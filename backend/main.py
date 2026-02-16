from urllib import response
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List
import json
import os
import re
from dotenv import load_dotenv

from database import get_db, init_db, User, Chat, Message
from schemas import (
    UserCreate, UserLogin, UserResponse, Token,
    ChatCreate, ChatResponse, MessageCreate, MessageResponse, ChatWithMessages
)
from auth import (
    verify_password, get_password_hash, create_access_token,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
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
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat

@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
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
    # Verify chat belongs to user
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
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
            # Generate a short title from the user's message
            title = message.content[:50]  # Take first 50 chars of meesage
            if len(message.content) > 50:
                title = title.rsplit(' ', 1)[0] + "..."  # Cut at last word
            chat.title = title
            db.commit()
    
    # Generate AI response
    try:
        from openai import OpenAI
        client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=120.0
        )
        
        # Get conversation history to provide context
        messages = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
        
        # Get the most recent workflow for context
        last_workflow_msg = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None)
        ).order_by(Message.created_at.desc()).first()
        
        # Build conversation with workflow context
        conversation = []
        for msg in messages:

            # For assistant messages with workflows, include the workflow in the content
            if msg.role == "assistant" and msg.workflow_data:
                # Include both the text and the workflow JSON in conversation
                content = f"{msg.content}\n\nCurrent workflow JSON:\n{msg.workflow_data}"
                conversation.append({"role": msg.role, "content": content})
            else:
                conversation.append({"role": msg.role, "content": msg.content})
        
        # Add system context about current workflow if it exists
        workflow_context = ""
        if last_workflow_msg and last_workflow_msg.workflow_data:
            workflow_context = f"\n\nCURRENT WORKFLOW (use this as your baseline for any modifications):\n{last_workflow_msg.workflow_data}\n\nWhen making changes, start with this exact workflow and ONLY modify what the user specifically requests."
        
        # Prompt sent to the OpenAI API
        system_message = {
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
        
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[system_message] + conversation,
            max_completion_tokens=5000
        )

        
        ai_content = response.choices[0].message.content
        
        # Better empty response handling with retry logic
        if not ai_content or len(ai_content.strip()) == 0:
            print("Warning: Empty response from AI, using fallback")
            # Use the previous workflow if it exists instead of defaulting to empty
            prev_message = db.query(Message).filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None)
            ).order_by(Message.created_at.desc()).first()
            
            if prev_message and prev_message.workflow_data:
                # Return previous workflow with explanation
                ai_message = Message(
                    chat_id=chat_id,
                    role="assistant",
                    content="I apologize, I encountered an issue generating a response. I've kept your previous workflow intact. Please try rephrasing your request or ask me to create a new workflow.",
                    workflow_data=prev_message.workflow_data
                )
                db.add(ai_message)
                db.commit()
                db.refresh(ai_message)
                return ai_message
            else:
                raise Exception("Empty response from AI model and no previous workflow available")
        
        # Try to extract workflow data if present from the AI response
        workflow_data = None
        display_content = ai_content  # Content to display in chat

        def extract_json_workflow(text: str):
            """Try multiple methods to extract JSON workflow"""
            
            # Method 1: Look for JSON in code blocks (```json {...} ```)
            code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if code_block_match:
                try:
                    data = json.loads(code_block_match.group(1))
                    if 'nodes' in data and 'edges' in data:
                        return code_block_match.group(1), code_block_match.group(0)
                except:
                    pass
            
            # Method 2: Look for JSON object anywhere with proper nesting
            # More aggressive pattern to handle nested objects
            json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
            json_matches = list(re.finditer(json_pattern, text, re.DOTALL))
            
            # Try matches from largest to smallest (prefer complete objects)
            json_matches.sort(key=lambda m: len(m.group(0)), reverse=True)
            
            for match in json_matches:
                try:
                    data = json.loads(match.group(0))
                    if 'nodes' in data and 'edges' in data:
                        # Verify nodes and edges are arrays
                        if isinstance(data['nodes'], list) and isinstance(data['edges'], list):
                            if len(data['nodes']) > 0:  # Ensure at least one node
                                return match.group(0), match.group(0)
                except:
                    continue
            
            return None, None

        try:
            extracted_json, full_match = extract_json_workflow(ai_content)
            
            if extracted_json:
                workflow_data = extracted_json
                print(f"Extracted workflow: {workflow_data}")
                
                # Validate JSON structure
                parsed = json.loads(workflow_data)
                if 'nodes' not in parsed or 'edges' not in parsed:
                    raise ValueError("Invalid workflow structure")
                
                # Verify we have actual content
                if len(parsed['nodes']) == 0:
                    raise ValueError("Workflow has no nodes")
                
                # Remove the matched JSON from display
                display_content = ai_content.replace(full_match, '').strip()
                
                # Clean up markdown artifacts
                display_content = re.sub(r'```\s*```', '', display_content).strip()
                display_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', display_content)
                
                # Default message if nothing left
                if not display_content or len(display_content) < 10:
                    display_content = "I've created a workflow visualization for you based on your requirements. You can see it in the visualization panel on the right."
            else:
                print("No valid workflow JSON found in response")
                # If no JSON found but user requested a workflow, regenerate with stricter prompt
                if any(keyword in message.content.lower() for keyword in ['workflow', 'flowchart', 'process', 'flujo', 'diagrama']):
                    print("User requested workflow but AI didn't provide JSON - using fallback")
                    # Create a simple fallback based on user's request
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
                    display_content = ai_content if ai_content else "I've created a basic workflow structure for you. You can refine it by describing the specific steps you need."

        except Exception as parse_error:
            print(f"JSON extraction error: {parse_error}")
            workflow_data = None
        
        # Save AI response
        ai_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=display_content,  # Use cleaned content without JSON
            workflow_data=workflow_data
        )
        db.add(ai_message)
        db.commit()
        db.refresh(ai_message)
        
        return ai_message
    except Exception as e:
        # If OpenAI fails, and error log is printed, and  then a fallback response is returned
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
        
        return ai_message
    
# Endpoint to update workflow data and position for a message
@app.patch("/messages/{message_id}/workflow")
def update_workflow(
    message_id: int,
    workflow_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get the message
    message = db.query(Message).join(Chat).filter(
        Message.id == message_id,
        Chat.user_id == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Update workflow data
    message.workflow_data = workflow_data.get('workflow_data')
    db.commit()
    
    return {"message": "Workflow updated successfully"}

# Endpoint for workflow history and undo
@app.get("/chats/{chat_id}/workflows/history")
def get_workflow_history(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all workflow versions in chronological order"""
    # Verify chat belongs to user
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
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
def undo_workflow(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revert to the previous workflow by removing the last assistant message"""
    # Verify chat belongs to user
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Get the last two messages (user request + AI response)
    last_messages = db.query(Message).filter(
        Message.chat_id == chat_id
    ).order_by(Message.created_at.desc()).limit(2).all()
    
    if len(last_messages) < 2:
        raise HTTPException(status_code=400, detail="No messages to undo")
    
    # Delete the last two messages
    for msg in last_messages:
        db.delete(msg)
    
    db.commit()
    
    # Get the previous workflow (if any)
    prev_workflow = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.role == "assistant",
        Message.workflow_data.isnot(None)
    ).order_by(Message.created_at.desc()).first()
    
    return {
        "message": "Undone successfully",
        "workflow_data": prev_workflow.workflow_data if prev_workflow else None
    }

@app.get("/")
def root():
    return {"message": "Handbook Project API is running", "version": "1.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
