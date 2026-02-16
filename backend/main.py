from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import timedelta, datetime
from typing import List, Optional, Dict, Set
import json
import os
import re
import asyncio
from dotenv import load_dotenv

from stream_parser import IncrementalWorkflowParser

from database import (
    get_db, init_db, User, Chat, Message, ChatCollaborator,
    CollaboratorRole, SessionLocal, WorkflowState, WorkflowOperation, WorkflowSnapshot
)
from schemas import (
    UserCreate, UserLogin, UserResponse, Token,
    ChatCreate, ChatResponse, MessageCreate, MessageResponse, ChatWithMessages,
    CollaboratorAdd, CollaboratorResponse, SharedChatResponse, UserSearchResponse,
    WorkflowOperationRequest, WorkflowOperationResponse, WorkflowStateResponse,
    VersionTimelineResponse, VersionEntry, RevertRequest, RevertResponse
)
from conflict_resolver import Operation, resolve as resolve_conflict
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
)

load_dotenv()

app = FastAPI(title="Handbook Project API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://frontend:3000",
        "https://handbook-frontend-production.up.railway.app",  # Railway frontend
        "https://handbook-backend-production.up.railway.app",  # Allow self
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    init_db()


# ============================================================
# WebSocket Connection Manager
# ============================================================

class ConnectionManager:
    """Manages WebSocket connections per chat room with presence tracking."""
    
    def __init__(self):
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}
        self.user_info: Dict[int, Dict[int, dict]] = {}
    
    async def connect(self, websocket: WebSocket, chat_id: int, user_id: int, username: str):
        await websocket.accept()
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = {}
            self.user_info[chat_id] = {}
        self.active_connections[chat_id][user_id] = websocket
        self.user_info[chat_id][user_id] = {"user_id": user_id, "username": username}
        await self.broadcast_presence(chat_id)
    
    def disconnect(self, chat_id: int, user_id: int):
        if chat_id in self.active_connections:
            self.active_connections[chat_id].pop(user_id, None)
            self.user_info[chat_id].pop(user_id, None)
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]
                del self.user_info[chat_id]
    
    async def broadcast_to_chat(self, chat_id: int, message: dict, exclude_user: int = None):
        if chat_id not in self.active_connections:
            return
        disconnected = []
        for uid, ws in self.active_connections[chat_id].items():
            if uid == exclude_user:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            self.disconnect(chat_id, uid)
    
    async def broadcast_presence(self, chat_id: int):
        if chat_id not in self.user_info:
            return
        presence_data = {
            "type": "presence",
            "chat_id": chat_id,
            "users": list(self.user_info[chat_id].values())
        }
        await self.broadcast_to_chat(chat_id, presence_data)
    
    def get_online_users(self, chat_id: int) -> list:
        if chat_id in self.user_info:
            return list(self.user_info[chat_id].values())
        return []


manager = ConnectionManager()


# ============================================================
# Per-Chat Lock Manager (serializes concurrent message processing)
# ============================================================

class ChatLockManager:
    """
    Provides one asyncio.Lock per chat_id so that only one message
    is processed at a time within a given chat.  Locks are created
    lazily and cleaned up when no longer held.
    """
    
    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._waiters: Dict[int, int] = {}
    
    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
            self._waiters[chat_id] = 0
        return self._locks[chat_id]
    
    async def acquire(self, chat_id: int, user_id: int, username: str):
        lock = self._get_lock(chat_id)
        self._waiters[chat_id] += 1
        
        if lock.locked():
            await manager.broadcast_to_chat(chat_id, {
                "type": "processing",
                "chat_id": chat_id,
                "status": "queued",
                "queued_by": user_id,
                "queued_by_username": username,
                "message": f"{username}'s request is waiting — another message is being processed"
            }, exclude_user=None)
        
        await lock.acquire()
        
        await manager.broadcast_to_chat(chat_id, {
            "type": "processing",
            "chat_id": chat_id,
            "status": "started",
            "processed_by": user_id,
            "processed_by_username": username,
            "message": f"Processing {username}'s message..."
        }, exclude_user=user_id)
    
    async def release(self, chat_id: int):
        if chat_id in self._locks:
            self._waiters[chat_id] -= 1
            self._locks[chat_id].release()
            
            if self._waiters[chat_id] <= 0:
                del self._locks[chat_id]
                del self._waiters[chat_id]
        
        await manager.broadcast_to_chat(chat_id, {
            "type": "processing",
            "chat_id": chat_id,
            "status": "done"
        })


chat_lock_manager = ChatLockManager()


# ============================================================
# Workflow JSON extraction helper (used by both sync and streaming paths)
# ============================================================

def extract_json_workflow(text: str):
    """
    Try multiple methods to extract a workflow JSON object from AI response text.
    Returns (json_string, full_match_string) or (None, None).
    """
    # Method 1: Look for JSON in code blocks (```json {...} ```)
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        try:
            data = json.loads(code_block_match.group(1))
            if 'nodes' in data and 'edges' in data:
                return code_block_match.group(1), code_block_match.group(0)
        except (json.JSONDecodeError, ValueError):
            pass

    # Method 2: Look for JSON object anywhere with proper nesting
    json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
    json_matches = list(re.finditer(json_pattern, text, re.DOTALL))

    json_matches.sort(key=lambda m: len(m.group(0)), reverse=True)

    for match in json_matches:
        try:
            data = json.loads(match.group(0))
            if 'nodes' in data and 'edges' in data:
                if isinstance(data['nodes'], list) and isinstance(data['edges'], list):
                    if len(data['nodes']) > 0:
                        return match.group(0), match.group(0)
        except (json.JSONDecodeError, ValueError):
            continue

    return None, None


# ============================================================
# System prompt builder (shared between sync and streaming paths)
# ============================================================

def _build_system_message(workflow_context: str) -> dict:
    """Build the system prompt for the OpenAI conversation."""
    return {
        "role": "system",
        "content": f"""You are a helpful assistant that helps companies design and visualize process workflows. You can communicate in English and Spanish.

    When the user requests a workflow:
    1. Provide a brief explanation of the workflow (1-3 sentences) in the user's language
    2. ALWAYS include the workflow as valid JSON in this exact format: {{"nodes": [{{"id": "1", "label": "Step name", "type": "start|process|decision|end"}}], "edges": [{{"from": "1", "to": "2"}}]}}
    3. NEVER return empty responses - always provide both explanation and JSON{workflow_context}

    Guidelines:
    - For NEW workflows: Create from scratch based on the user's description
    - For UPDATES/MODIFICATIONS: 
    * CRITICAL: START WITH THE CURRENT WORKFLOW JSON PROVIDED ABOVE
    * ONLY modify the specific nodes/edges the user explicitly mentioned
    * Copy all other nodes and edges EXACTLY as they appear in the current workflow
    * Preserve all node IDs, labels, types, and edge connections that aren't being changed
    * If updating ONE node label, copy all other nodes with identical IDs and labels
    * If adding ONE node, copy the entire current workflow and append the new node with the next sequential ID
    * If removing ONE node:
      - Remove the node from the nodes array
      - Remove all edges that connect to/from that node
      - If removing a DECISION node that creates branches:
        a) Find all nodes that were AFTER the decision (nodes that the decision pointed to)
        b) Find what came BEFORE the decision (the parent node)
        c) Connect the parent node directly to the FIRST branch path (skip the decision)
        d) Merge the branches back into the main flow at their natural convergence point
        e) Example: A→Decision→[B,C]→D becomes A→B→D (selecting primary branch)
      - Ensure no orphaned nodes (nodes with no path from start)
    * Think of it as copy-paste with minimal edits, not reconstruction
    - Use sequential IDs starting from "1" for NEW workflows
    - MUST include exactly one "start" node and at least one "end" node
    - Use "decision" type for branching points (if/else scenarios)
    - Ensure all edges connect existing node IDs
    - Keep labels clear and concise (max 80 characters)
    - Node labels must be based on user's language: either English or Spanish

    IMPORTANT FOR MODIFICATIONS:
    - When user says "change/cambiar X", "update/actualizar X", "modify/modificar X" - ONLY change X
    - The current workflow is your STARTING POINT - copy it and make minimal edits
    - Do not reorganize, renumber, reorder, or restructure unchanged parts
    - Imagine you're using find-and-replace, not rewriting from scratch
    - Preserve the exact structure and IDs from the current workflow
    
    SPECIAL CASE - Removing Decision Nodes:
    - When removing a decision node, intelligently merge the branches:
      1. Identify the parent node (what connects TO the decision)
      2. Identify the child nodes (what the decision connects TO)
      3. Choose the primary/main branch (usually the first/main path)
      4. Create edge from parent → primary branch's first node
      5. Keep the flow intact by maintaining downstream connections
      6. Remove alternate branches only if they don't rejoin the main flow
    - Goal: Maintain a coherent, linear flow after removing the decision point

    CRITICAL: EVERY workflow request MUST include valid JSON with at least:
    - One "start" node
    - One "end" node  
    - At least one connecting edge
    - Proper node IDs (no duplicates)

    Spanish keywords to recognize: flujo, diagrama, proceso, flujo de trabajo, flowchart
    English keywords: workflow, flowchart, process, flow

    ALWAYS provide both explanation AND valid JSON. Never provide responses without JSON when a workflow is requested."""
    }


def _build_conversation_history(messages, last_workflow_msg):
    """Build conversation array and workflow context string from message history."""
    conversation = []
    for msg in messages:
        if msg.role == "assistant" and msg.workflow_data:
            content = f"{msg.content}\n\nCurrent workflow JSON:\n{msg.workflow_data}"
            conversation.append({"role": msg.role, "content": content})
        else:
            conversation.append({"role": msg.role, "content": msg.content})

    workflow_context = ""
    if last_workflow_msg and last_workflow_msg.workflow_data:
        workflow_context = (
            f"\n\nCURRENT WORKFLOW (use this as your baseline for any modifications):\n"
            f"{last_workflow_msg.workflow_data}\n\n"
            f"When making changes, start with this exact workflow and ONLY modify what the user specifically requests."
        )

    return conversation, workflow_context


# ============================================================
# Helper: Check if user has access to a chat (owner or collaborator)
# ============================================================

def get_chat_with_access(
    chat_id: int, 
    user: User, 
    db: Session, 
    require_role: str = None
) -> Chat:
    """
    Returns the chat if the user is the owner or a collaborator.
    If require_role is set, collaborators must have that role (e.g. 'editor').
    Raises 404 if chat doesn't exist or user has no access.
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if chat.user_id == user.id:
        return chat
    
    collab = db.query(ChatCollaborator).filter(
        ChatCollaborator.chat_id == chat_id,
        ChatCollaborator.user_id == user.id
    ).first()
    
    if not collab:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if require_role and collab.role != require_role:
        raise HTTPException(
            status_code=403, 
            detail=f"You need '{require_role}' access to perform this action"
        )
    
    return chat


# Authentication endpoints
@app.post("/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    # Create new user if user does not exist
    hashed_password = get_password_hash(user.password)
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# Login endpoint
@app.post("/auth/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username"
        )
    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# Chat endpoints
@app.get("/chats", response_model=List[ChatResponse])
def get_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.updated_at.desc()).all()
    return chats

@app.get("/chats/shared", response_model=List[SharedChatResponse])
def get_shared_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all chats that have been shared with the current user."""
    collabs = db.query(ChatCollaborator).filter(
        ChatCollaborator.user_id == current_user.id
    ).all()
    
    result = []
    for collab in collabs:
        chat = db.query(Chat).filter(Chat.id == collab.chat_id).first()
        if chat:
            owner = db.query(User).filter(User.id == chat.user_id).first()
            result.append(SharedChatResponse(
                id=chat.id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                owner_id=chat.user_id,
                owner_username=owner.username if owner else "Unknown",
                my_role=collab.role
            ))
    
    result.sort(key=lambda x: x.updated_at, reverse=True)
    return result

@app.post("/chats", response_model=ChatResponse)
def create_chat(chat: ChatCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_chat = Chat(
        user_id=current_user.id,
        title=chat.title
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    return new_chat

@app.get("/chats/{chat_id}", response_model=ChatWithMessages)
def get_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = get_chat_with_access(chat_id, current_user, db)
    return chat

@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")
    db.delete(chat)
    db.commit()
    return {"message": "Chat deleted successfully"}

# Message endpoints
@app.post("/chats/{chat_id}/messages", response_model=MessageResponse)
async def create_message(
    chat_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = get_chat_with_access(chat_id, current_user, db, require_role=None)
    
    # Acquire per-chat lock — serializes concurrent messages so the AI
    # always sees the full conversation history including prior requests.
    await chat_lock_manager.acquire(chat_id, current_user.id, current_user.username)
    
    try:
        # Re-fetch the chat inside the lock so we see any changes
        # committed by a previously-queued request.
        db.expire_all()
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        
        # Save user message
        user_message = Message(
            chat_id=chat_id,
            role="user",
            content=message.content
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
        
        # Update chat title if it's still "New Conversation" and this is the first message
        if chat.title == "New Conversation":
            message_count = db.query(Message).filter(Message.chat_id == chat_id).count()
            if message_count == 1:  # First message
                title = message.content[:50]
                if len(message.content) > 50:
                    title = title.rsplit(' ', 1)[0] + "..."
                chat.title = title
                db.commit()
        
        return await _generate_ai_response(chat_id, message, user_message, current_user, db)
    finally:
        await chat_lock_manager.release(chat_id)


async def _generate_ai_response(
    chat_id: int,
    message: MessageCreate,
    user_message: Message,
    current_user: User,
    db: Session
) -> Message:
    """Separated AI response logic so the lock wrapper stays clean."""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=120.0
        )

        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
        last_workflow_msg = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None)
        ).order_by(Message.created_at.desc()).first()

        conversation, workflow_context = _build_conversation_history(messages, last_workflow_msg)
        system_message = _build_system_message(workflow_context)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[system_message] + conversation,
            max_completion_tokens=5000
        )

        ai_content = response.choices[0].message.content

        if not ai_content or len(ai_content.strip()) == 0:
            print("Warning: Empty response from AI, using fallback")
            prev_message = db.query(Message).filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None)
            ).order_by(Message.created_at.desc()).first()

            if prev_message and prev_message.workflow_data:
                ai_message = Message(
                    chat_id=chat_id,
                    role="assistant",
                    content="I apologize, I encountered an issue generating a response. I've kept your previous workflow intact. Please try rephrasing your request or ask me to create a new workflow.",
                    workflow_data=prev_message.workflow_data
                )
                db.add(ai_message)
                db.commit()
                db.refresh(ai_message)
                if ai_message.workflow_data:
                    _ensure_workflow_state(chat_id, ai_message.workflow_data, current_user.id, db)
                return ai_message
            else:
                raise Exception("Empty response from AI model and no previous workflow available")

        workflow_data = None
        display_content = ai_content

        try:
            extracted_json, full_match = extract_json_workflow(ai_content)

            if extracted_json:
                workflow_data = extracted_json
                parsed = json.loads(workflow_data)
                if 'nodes' not in parsed or 'edges' not in parsed:
                    raise ValueError("Invalid workflow structure")
                if len(parsed['nodes']) == 0:
                    raise ValueError("Workflow has no nodes")

                display_content = ai_content.replace(full_match, '').strip()
                display_content = re.sub(r'```\s*```', '', display_content).strip()
                display_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', display_content)

                if not display_content or len(display_content) < 10:
                    display_content = "I've created a workflow visualization for you based on your requirements. You can see it in the visualization panel on the right."
            else:
                if any(keyword in message.content.lower() for keyword in ['workflow', 'flowchart', 'process', 'flujo', 'diagrama']):
                    workflow_data = json.dumps({
                        "nodes": [
                            {"id": "1", "label": "Start", "type": "start"},
                            {"id": "2", "label": "Process request", "type": "process"},
                            {"id": "3", "label": "Complete", "type": "end"}
                        ],
                        "edges": [
                            {"from": "1", "to": "2"},
                            {"from": "2", "to": "3"}
                        ]
                    })
                    display_content = ai_content if ai_content else "I've created a basic workflow structure for you."

        except Exception as parse_error:
            print(f"JSON extraction error: {parse_error}")
            workflow_data = None

        ai_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=display_content,
            workflow_data=workflow_data
        )
        db.add(ai_message)
        db.commit()
        db.refresh(ai_message)

        if ai_message.workflow_data:
            _ensure_workflow_state(chat_id, ai_message.workflow_data, current_user.id, db)

        ws_state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()

        await manager.broadcast_to_chat(chat_id, {
            "type": "new_message",
            "chat_id": chat_id,
            "sender_id": current_user.id,
            "sender_username": current_user.username,
            "workflow_version": ws_state.version if ws_state else None,
            "messages": [
                {
                    "id": user_message.id,
                    "chat_id": chat_id,
                    "role": "user",
                    "content": user_message.content,
                    "workflow_data": None,
                    "created_at": user_message.created_at.isoformat()
                },
                {
                    "id": ai_message.id,
                    "chat_id": chat_id,
                    "role": "assistant",
                    "content": ai_message.content,
                    "workflow_data": ai_message.workflow_data,
                    "created_at": ai_message.created_at.isoformat()
                }
            ]
        }, exclude_user=current_user.id)

        return ai_message
    except Exception as e:
        print(f"OpenAI Error: {type(e).__name__}: {str(e)}")

        fallback_workflow = json.dumps({
            "nodes": [
                {"id": "1", "label": "Start", "type": "start"},
                {"id": "2", "label": "Process Request", "type": "process"},
                {"id": "3", "label": "Decision Point", "type": "decision"},
                {"id": "4", "label": "Complete", "type": "end"}
            ],
            "edges": [
                {"from": "1", "to": "2"},
                {"from": "2", "to": "3"},
                {"from": "3", "to": "4"}
            ]
        })

        ai_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=f"I can help you design a workflow. Here's a sample process visualization. (Note: OpenAI API is not configured - {str(e)})",
            workflow_data=fallback_workflow
        )
        db.add(ai_message)
        db.commit()
        db.refresh(ai_message)

        if ai_message.workflow_data:
            _ensure_workflow_state(chat_id, ai_message.workflow_data, current_user.id, db)

        return ai_message


# ============================================================
# Streaming Message Endpoint (SSE)
# ============================================================

@app.post("/chats/{chat_id}/messages/stream")
async def stream_message(
    chat_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message and receive the AI response as a Server-Sent Events stream.

    Events emitted:
      stream_start       – generation begins (includes user_message_id)
      text_chunk         – a piece of the AI's text response
      node_add           – a new workflow node was detected
      edge_add           – a new workflow edge was detected
      workflow_complete  – final validated workflow JSON + display text
      stream_end         – generation finished (includes message_id, workflow_version)
      error              – something went wrong
    """
    chat = get_chat_with_access(chat_id, current_user, db, require_role=None)

    await chat_lock_manager.acquire(chat_id, current_user.id, current_user.username)

    # Save user message BEFORE entering the async generator so the
    # dependency-injected db session is still valid.
    db.expire_all()
    chat = db.query(Chat).filter(Chat.id == chat_id).first()

    user_message = Message(
        chat_id=chat_id,
        role="user",
        content=message.content
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    if chat.title == "New Conversation":
        message_count = db.query(Message).filter(Message.chat_id == chat_id).count()
        if message_count == 1:
            title = message.content[:50]
            if len(message.content) > 50:
                title = title.rsplit(' ', 1)[0] + "..."
            chat.title = title
            db.commit()

    # Capture values the generator needs (the DI session may close).
    user_id = current_user.id
    username = current_user.username
    user_msg_id = user_message.id
    user_msg_content = user_message.content
    user_msg_created_at = user_message.created_at
    msg_content_lower = message.content.lower()

    async def event_generator():
        gen_db = SessionLocal()
        try:
            yield f"event: stream_start\ndata: {json.dumps({'user_message_id': user_msg_id})}\n\n"

            # ----- build conversation context -----
            all_messages = gen_db.query(Message).filter(
                Message.chat_id == chat_id
            ).order_by(Message.created_at).all()

            last_workflow_msg = gen_db.query(Message).filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None)
            ).order_by(Message.created_at.desc()).first()

            conversation, workflow_context = _build_conversation_history(
                all_messages, last_workflow_msg
            )
            system_msg = _build_system_message(workflow_context)

            # ----- OpenAI streaming call (async to avoid blocking the event loop) -----
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                timeout=120.0
            )

            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_msg] + conversation,
                max_completion_tokens=5000,
                stream=True
            )

            parser = IncrementalWorkflowParser()
            full_content = ""

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice or not choice.delta or not choice.delta.content:
                    continue

                token = choice.delta.content
                full_content += token

                # Send text chunk
                yield f"event: text_chunk\ndata: {json.dumps({'content': token})}\n\n"

                # Detect newly completed nodes / edges
                new_nodes, new_edges = parser.feed(token)
                for node in new_nodes:
                    yield f"event: node_add\ndata: {json.dumps({'node': node})}\n\n"
                for edge in new_edges:
                    yield f"event: edge_add\ndata: {json.dumps({'edge': edge})}\n\n"

            # ----- post-stream processing -----
            if not full_content or len(full_content.strip()) == 0:
                prev_msg = gen_db.query(Message).filter(
                    Message.chat_id == chat_id,
                    Message.role == "assistant",
                    Message.workflow_data.isnot(None)
                ).order_by(Message.created_at.desc()).first()

                if prev_msg and prev_msg.workflow_data:
                    workflow_data = prev_msg.workflow_data
                    display_content = "I apologize, I encountered an issue. I've kept your previous workflow intact."
                else:
                    yield f"event: error\ndata: {json.dumps({'error': 'Empty AI response'})}\n\n"
                    return
            else:
                workflow_data = None
                display_content = full_content

                try:
                    extracted_json, full_match = extract_json_workflow(full_content)
                    if extracted_json:
                        workflow_data = extracted_json
                        parsed = json.loads(workflow_data)
                        if 'nodes' not in parsed or 'edges' not in parsed or len(parsed['nodes']) == 0:
                            raise ValueError("Invalid workflow structure")

                        display_content = full_content.replace(full_match, '').strip()
                        display_content = re.sub(r'```\s*```', '', display_content).strip()
                        display_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', display_content)
                        if not display_content or len(display_content) < 10:
                            display_content = "I've created a workflow visualization for you based on your requirements."
                    else:
                        if any(kw in msg_content_lower for kw in ['workflow', 'flowchart', 'process', 'flujo', 'diagrama']):
                            workflow_data = json.dumps({
                                "nodes": [
                                    {"id": "1", "label": "Start", "type": "start"},
                                    {"id": "2", "label": "Process request", "type": "process"},
                                    {"id": "3", "label": "Complete", "type": "end"}
                                ],
                                "edges": [
                                    {"from": "1", "to": "2"},
                                    {"from": "2", "to": "3"}
                                ]
                            })
                            display_content = full_content if full_content.strip() else "I've created a basic workflow."
                except Exception as parse_err:
                    print(f"Stream JSON extraction error: {parse_err}")
                    workflow_data = None

            # ----- persist assistant message -----
            ai_message = Message(
                chat_id=chat_id,
                role="assistant",
                content=display_content,
                workflow_data=workflow_data
            )
            gen_db.add(ai_message)
            gen_db.commit()
            gen_db.refresh(ai_message)

            if ai_message.workflow_data:
                _ensure_workflow_state(chat_id, ai_message.workflow_data, user_id, gen_db)

            ws_state = gen_db.query(WorkflowState).filter(
                WorkflowState.chat_id == chat_id
            ).first()

            # Send the final workflow (validated & cleaned)
            yield (
                f"event: workflow_complete\n"
                f"data: {json.dumps({'workflow_data': workflow_data, 'display_content': display_content})}\n\n"
            )

            yield (
                f"event: stream_end\n"
                f"data: {json.dumps({'message_id': ai_message.id, 'workflow_version': ws_state.version if ws_state else None})}\n\n"
            )

            # ----- broadcast to collaborators via WebSocket -----
            await manager.broadcast_to_chat(chat_id, {
                "type": "new_message",
                "chat_id": chat_id,
                "sender_id": user_id,
                "sender_username": username,
                "workflow_version": ws_state.version if ws_state else None,
                "messages": [
                    {
                        "id": user_msg_id,
                        "chat_id": chat_id,
                        "role": "user",
                        "content": user_msg_content,
                        "workflow_data": None,
                        "created_at": user_msg_created_at.isoformat()
                    },
                    {
                        "id": ai_message.id,
                        "chat_id": chat_id,
                        "role": "assistant",
                        "content": ai_message.content,
                        "workflow_data": ai_message.workflow_data,
                        "created_at": ai_message.created_at.isoformat()
                    }
                ]
            }, exclude_user=user_id)

        except Exception as e:
            print(f"Streaming error: {type(e).__name__}: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            gen_db.close()
            await chat_lock_manager.release(chat_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# Endpoint to update workflow data and position for a message
@app.patch("/messages/{message_id}/workflow")
async def update_workflow(
    message_id: int,
    workflow_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    chat = get_chat_with_access(msg.chat_id, current_user, db)
    
    new_data = workflow_data.get('workflow_data')
    msg.workflow_data = new_data
    db.commit()
    
    await manager.broadcast_to_chat(msg.chat_id, {
        "type": "workflow_update",
        "chat_id": msg.chat_id,
        "message_id": message_id,
        "workflow_data": new_data,
        "updated_by": current_user.id,
        "updated_by_username": current_user.username
    }, exclude_user=current_user.id)
    
    return {"message": "Workflow updated successfully"}


# ============================================================
# Version-Based Conflict Resolution Endpoints
# ============================================================

def _ensure_workflow_state(
    chat_id: int, data: str, user_id: int, db: Session,
    description: str = "AI-generated workflow"
) -> WorkflowState:
    """
    Create or update WorkflowState and save a snapshot.
    If the pointer was in the middle of the history (user had undone),
    truncate future snapshots before appending — git-style branching.
    """
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if state:
        # Truncate any snapshots ahead of the current pointer
        db.query(WorkflowSnapshot).filter(
            WorkflowSnapshot.chat_id == chat_id,
            WorkflowSnapshot.version > state.current_version
        ).delete(synchronize_session=False)
        
        state.version += 1
        state.current_version = state.version
        state.data = data
        state.updated_by = user_id
    else:
        state = WorkflowState(
            chat_id=chat_id,
            version=1,
            current_version=1,
            data=data,
            updated_by=user_id
        )
        db.add(state)
        db.flush()
    
    snapshot = WorkflowSnapshot(
        chat_id=chat_id,
        version=state.version,
        data=data,
        description=description,
        created_by=user_id
    )
    db.add(snapshot)
    db.commit()
    db.refresh(state)
    return state


@app.get("/chats/{chat_id}/workflow/state", response_model=WorkflowStateResponse)
def get_workflow_state(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current versioned workflow state for a chat.
    Clients use the returned version as base_version for subsequent operations.
    """
    get_chat_with_access(chat_id, current_user, db)
    
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        last_workflow_msg = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None)
        ).order_by(Message.created_at.desc()).first()
        
        if not last_workflow_msg:
            raise HTTPException(status_code=404, detail="No workflow exists for this chat")
        
        state = _ensure_workflow_state(
            chat_id, last_workflow_msg.workflow_data, current_user.id, db
        )
    
    return WorkflowStateResponse(
        chat_id=chat_id,
        version=state.current_version,
        max_version=state.version,
        data=state.data,
        updated_at=state.updated_at,
        updated_by=state.updated_by
    )


@app.post("/chats/{chat_id}/workflow/operations", response_model=WorkflowOperationResponse)
async def apply_workflow_operations(
    chat_id: int,
    request: WorkflowOperationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Apply operations to a workflow with version-based conflict resolution.
    
    - If base_version matches server → apply directly.
    - If behind but operations don't conflict → auto-merge.
    - If conflicting → reject with conflict details + latest state.
    """
    get_chat_with_access(chat_id, current_user, db)
    
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        last_workflow_msg = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None)
        ).order_by(Message.created_at.desc()).first()
        
        if not last_workflow_msg:
            raise HTTPException(status_code=404, detail="No workflow exists for this chat")
        
        state = _ensure_workflow_state(
            chat_id, last_workflow_msg.workflow_data, current_user.id, db
        )
    
    incoming_ops = [
        Operation(op_type=op.op_type, payload=op.payload)
        for op in request.operations
    ]
    
    op_log = []
    if request.base_version < state.version:
        op_records = db.query(WorkflowOperation).filter(
            WorkflowOperation.chat_id == chat_id,
            WorkflowOperation.version_after > request.base_version,
            WorkflowOperation.version_after <= state.version,
            WorkflowOperation.status == "applied"
        ).order_by(WorkflowOperation.version_after.asc()).all()
        
        op_log = [{"op_data": r.op_data} for r in op_records]
    
    result = resolve_conflict(
        current_data=state.data,
        current_version=state.version,
        base_version=request.base_version,
        incoming_ops=incoming_ops,
        op_log=op_log
    )
    
    if result.status == "conflict":
        return WorkflowOperationResponse(
            status="conflict",
            version=state.current_version,
            data=state.data,
            conflicts=result.conflicts
        )
    
    # Truncate future snapshots if pointer was in the middle
    db.query(WorkflowSnapshot).filter(
        WorkflowSnapshot.chat_id == chat_id,
        WorkflowSnapshot.version > state.current_version
    ).delete(synchronize_session=False)
    
    state.data = result.new_data
    state.version = result.new_version
    state.current_version = result.new_version
    state.updated_by = current_user.id
    
    op_desc = ", ".join(op.op_type for op in incoming_ops)
    
    op_record = WorkflowOperation(
        chat_id=chat_id,
        user_id=current_user.id,
        version_before=request.base_version,
        version_after=result.new_version,
        op_type=op_desc,
        op_data=json.dumps([
            {"op_type": op.op_type, "payload": op.payload}
            for op in incoming_ops
        ]),
        status=result.status
    )
    db.add(op_record)
    
    snapshot = WorkflowSnapshot(
        chat_id=chat_id,
        version=result.new_version,
        data=result.new_data,
        description=f"{current_user.username}: {op_desc}",
        created_by=current_user.id
    )
    db.add(snapshot)
    
    last_msg = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.role == "assistant",
        Message.workflow_data.isnot(None)
    ).order_by(Message.created_at.desc()).first()
    if last_msg:
        last_msg.workflow_data = result.new_data
    
    db.commit()
    
    await manager.broadcast_to_chat(chat_id, {
        "type": "workflow_op",
        "chat_id": chat_id,
        "version": result.new_version,
        "data": result.new_data,
        "operations": [
            {"op_type": op.op_type, "payload": op.payload}
            for op in incoming_ops
        ],
        "applied_by": current_user.id,
        "applied_by_username": current_user.username,
        "status": result.status
    }, exclude_user=current_user.id)
    
    return WorkflowOperationResponse(
        status=result.status,
        version=result.new_version,
        data=result.new_data,
        conflicts=[]
    )


# Endpoint for workflow history and undo
@app.get("/chats/{chat_id}/workflows/history")
def get_workflow_history(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all workflow versions in chronological order"""
    chat = get_chat_with_access(chat_id, current_user, db)
    
    # Get all messages with workflows
    messages = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.role == "assistant",
        Message.workflow_data.isnot(None)
    ).order_by(Message.created_at.desc()).all()
    
    return [{
        "id": msg.id,
        "workflow_data": msg.workflow_data,
        "created_at": msg.created_at
    } for msg in messages]

@app.post("/chats/{chat_id}/workflows/undo")
async def undo_workflow(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revert to the previous workflow by removing the last assistant message"""
    chat = get_chat_with_access(chat_id, current_user, db)
    
    # Lock so undo cannot race with an in-flight message generation
    await chat_lock_manager.acquire(chat_id, current_user.id, current_user.username)
    try:
        db.expire_all()
        
        last_messages = db.query(Message).filter(
            Message.chat_id == chat_id
        ).order_by(Message.created_at.desc()).limit(2).all()
        
        if len(last_messages) < 2:
            raise HTTPException(status_code=400, detail="No messages to undo")
        
        for msg in last_messages:
            db.delete(msg)
        
        db.commit()
        
        prev_workflow = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None)
        ).order_by(Message.created_at.desc()).first()
        
        result = {
            "message": "Undone successfully",
            "workflow_data": prev_workflow.workflow_data if prev_workflow else None
        }
        
        await manager.broadcast_to_chat(chat_id, {
            "type": "undo",
            "chat_id": chat_id,
            "undone_by": current_user.id,
            "undone_by_username": current_user.username,
            "workflow_data": result["workflow_data"]
        }, exclude_user=current_user.id)
        
        return result
    finally:
        await chat_lock_manager.release(chat_id)


# ============================================================
# Version Control Endpoints (undo / redo / revert / timeline)
# ============================================================

@app.get("/chats/{chat_id}/workflow/versions", response_model=VersionTimelineResponse)
def get_version_timeline(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return every saved version of the workflow so the client can
    render a timeline and jump to any point.
    """
    get_chat_with_access(chat_id, current_user, db)
    
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    cur_ver = state.current_version if state else 0
    
    snapshots = db.query(WorkflowSnapshot).filter(
        WorkflowSnapshot.chat_id == chat_id
    ).order_by(WorkflowSnapshot.version.asc()).all()
    
    entries: List[VersionEntry] = []
    for snap in snapshots:
        creator = db.query(User).filter(User.id == snap.created_by).first() if snap.created_by else None
        entries.append(VersionEntry(
            version=snap.version,
            description=snap.description,
            created_by=snap.created_by,
            created_by_username=creator.username if creator else None,
            created_at=snap.created_at,
            is_current=(snap.version == cur_ver)
        ))
    
    return VersionTimelineResponse(
        chat_id=chat_id,
        current_version=cur_ver,
        versions=entries
    )


@app.post("/chats/{chat_id}/workflow/revert", response_model=RevertResponse)
async def revert_to_version(
    chat_id: int,
    request: RevertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Move the current_version pointer to an existing snapshot.
    No new snapshots are created — undo/redo just moves the pointer.
    """
    get_chat_with_access(chat_id, current_user, db)
    
    snapshot = db.query(WorkflowSnapshot).filter(
        WorkflowSnapshot.chat_id == chat_id,
        WorkflowSnapshot.version == request.target_version
    ).first()
    
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=f"Version {request.target_version} not found"
        )
    
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="No workflow state found")
    
    # Just move the pointer — no version increment, no new snapshot
    state.current_version = request.target_version
    state.data = snapshot.data
    state.updated_by = current_user.id
    
    last_msg = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.role == "assistant",
        Message.workflow_data.isnot(None)
    ).order_by(Message.created_at.desc()).first()
    if last_msg:
        last_msg.workflow_data = snapshot.data
    
    db.commit()
    
    await manager.broadcast_to_chat(chat_id, {
        "type": "version_revert",
        "chat_id": chat_id,
        "current_version": state.current_version,
        "max_version": state.version,
        "target_version": request.target_version,
        "data": snapshot.data,
        "reverted_by": current_user.id,
        "reverted_by_username": current_user.username,
    }, exclude_user=current_user.id)
    
    return RevertResponse(
        version=state.current_version,
        data=snapshot.data,
        message=f"Moved to version {request.target_version}"
    )


@app.get("/chats/{chat_id}/workflow/versions/{version}")
def get_version_snapshot(
    chat_id: int,
    version: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Preview a specific version without reverting."""
    get_chat_with_access(chat_id, current_user, db)
    
    snapshot = db.query(WorkflowSnapshot).filter(
        WorkflowSnapshot.chat_id == chat_id,
        WorkflowSnapshot.version == version
    ).first()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    
    creator = db.query(User).filter(User.id == snapshot.created_by).first() if snapshot.created_by else None
    
    return {
        "version": snapshot.version,
        "data": snapshot.data,
        "description": snapshot.description,
        "created_by_username": creator.username if creator else None,
        "created_at": snapshot.created_at.isoformat()
    }


# ============================================================
# Collaboration Endpoints
# ============================================================

@app.get("/users/search", response_model=List[UserSearchResponse])
def search_users(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search for users by username or email to share chats with."""
    users = db.query(User).filter(
        User.id != current_user.id,
        or_(
            User.username.ilike(f"%{q}%"),
            User.email.ilike(f"%{q}%")
        )
    ).limit(10).all()
    return users

@app.post("/chats/{chat_id}/collaborators", response_model=CollaboratorResponse)
async def add_collaborator(
    chat_id: int,
    collab: CollaboratorAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a collaborator to a chat. Only the chat owner can do this."""
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")
    
    target_user = db.query(User).filter(User.username == collab.username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{collab.username}' not found")
    
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a collaborator")
    
    existing = db.query(ChatCollaborator).filter(
        ChatCollaborator.chat_id == chat_id,
        ChatCollaborator.user_id == target_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a collaborator")
    
    new_collab = ChatCollaborator(
        chat_id=chat_id,
        user_id=target_user.id,
        role=collab.role,
        invited_by=current_user.id
    )
    db.add(new_collab)
    db.commit()
    db.refresh(new_collab)
    
    await manager.broadcast_to_chat(chat_id, {
        "type": "collaborator_added",
        "chat_id": chat_id,
        "user_id": target_user.id,
        "username": target_user.username,
        "role": collab.role
    })
    
    return CollaboratorResponse(
        id=new_collab.id,
        user_id=target_user.id,
        username=target_user.username,
        email=target_user.email,
        role=new_collab.role,
        invited_by=current_user.id,
        inviter_username=current_user.username,
        created_at=new_collab.created_at
    )

@app.get("/chats/{chat_id}/collaborators", response_model=List[CollaboratorResponse])
def get_collaborators(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all collaborators for a chat. Accessible by owner and collaborators."""
    chat = get_chat_with_access(chat_id, current_user, db)
    
    collabs = db.query(ChatCollaborator).filter(ChatCollaborator.chat_id == chat_id).all()
    result = []
    for c in collabs:
        user = db.query(User).filter(User.id == c.user_id).first()
        inviter = db.query(User).filter(User.id == c.invited_by).first()
        if user:
            result.append(CollaboratorResponse(
                id=c.id,
                user_id=c.user_id,
                username=user.username,
                email=user.email,
                role=c.role,
                invited_by=c.invited_by,
                inviter_username=inviter.username if inviter else "Unknown",
                created_at=c.created_at
            ))
    return result

@app.delete("/chats/{chat_id}/collaborators/{user_id}")
async def remove_collaborator(
    chat_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a collaborator. Owner can remove anyone; collaborators can remove themselves."""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    is_owner = chat.user_id == current_user.id
    is_self = user_id == current_user.id
    
    if not is_owner and not is_self:
        raise HTTPException(status_code=403, detail="Only the owner can remove other collaborators")
    
    collab = db.query(ChatCollaborator).filter(
        ChatCollaborator.chat_id == chat_id,
        ChatCollaborator.user_id == user_id
    ).first()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    removed_user = db.query(User).filter(User.id == user_id).first()
    db.delete(collab)
    db.commit()
    
    await manager.broadcast_to_chat(chat_id, {
        "type": "collaborator_removed",
        "chat_id": chat_id,
        "user_id": user_id,
        "username": removed_user.username if removed_user else "Unknown"
    })
    
    return {"message": "Collaborator removed successfully"}

@app.patch("/chats/{chat_id}/collaborators/{user_id}")
def update_collaborator_role(
    chat_id: int,
    user_id: int,
    role_update: CollaboratorAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a collaborator's role. Only the chat owner can do this."""
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")
    
    collab = db.query(ChatCollaborator).filter(
        ChatCollaborator.chat_id == chat_id,
        ChatCollaborator.user_id == user_id
    ).first()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    
    collab.role = role_update.role
    db.commit()
    
    return {"message": f"Role updated to {role_update.role}"}

@app.get("/chats/{chat_id}/online")
def get_online_users(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get currently online users in a chat."""
    get_chat_with_access(chat_id, current_user, db)
    return {"users": manager.get_online_users(chat_id)}


# ============================================================
# WebSocket Endpoint
# ============================================================

@app.websocket("/ws/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: int, token: str = Query(...)):
    """
    WebSocket connection for real-time chat updates.
    Authenticate via token query parameter.
    """
    from jose import JWTError, jwt as jose_jwt
    
    db = SessionLocal()
    try:
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return
        
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            await websocket.close(code=4004, reason="Chat not found")
            return
        
        is_owner = chat.user_id == user.id
        is_collab = db.query(ChatCollaborator).filter(
            ChatCollaborator.chat_id == chat_id,
            ChatCollaborator.user_id == user.id
        ).first()
        
        if not is_owner and not is_collab:
            await websocket.close(code=4003, reason="Access denied")
            return
        
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return
    finally:
        db.close()
    
    await manager.connect(websocket, chat_id, user.id, user.username)
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "typing":
                await manager.broadcast_to_chat(chat_id, {
                    "type": "typing",
                    "chat_id": chat_id,
                    "user_id": user.id,
                    "username": user.username,
                    "is_typing": data.get("is_typing", False)
                }, exclude_user=user.id)
    except WebSocketDisconnect:
        manager.disconnect(chat_id, user.id)
        await manager.broadcast_presence(chat_id)
    except Exception:
        manager.disconnect(chat_id, user.id)
        await manager.broadcast_presence(chat_id)


@app.get("/")
def root():
    return {"message": "Handbook Project API is running", "version": "1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
