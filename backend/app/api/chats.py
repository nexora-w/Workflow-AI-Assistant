"""Chat and message endpoints."""

import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.models import User, Chat, Message, WorkflowState
from app.schemas import (
    ChatCreate,
    ChatResponse,
    ChatWithMessages,
    MessageCreate,
    MessageResponse,
    SharedChatResponse,
)
from app.services.chat import get_chat_with_access
from app.services.ai import (
    build_system_message,
    build_conversation_history,
    extract_json_workflow,
    generate_ai_response,
    WORKFLOW_KEYWORDS,
)
from app.services.workflow import ensure_workflow_state
from app.websocket import connection_manager, chat_lock_manager
from app.utils import IncrementalWorkflowParser

router = APIRouter(tags=["chats"])


@router.get("/chats", response_model=List[ChatResponse])
def get_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.updated_at.desc()).all()


@router.get("/chats/shared", response_model=List[SharedChatResponse])
def get_shared_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models import ChatCollaborator

    collabs = db.query(ChatCollaborator).filter(ChatCollaborator.user_id == current_user.id).all()
    result = []
    for collab in collabs:
        chat = db.query(Chat).filter(Chat.id == collab.chat_id).first()
        if chat:
            owner = db.query(User).filter(User.id == chat.user_id).first()
            result.append(
                SharedChatResponse(
                    id=chat.id,
                    title=chat.title,
                    created_at=chat.created_at,
                    updated_at=chat.updated_at,
                    owner_id=chat.user_id,
                    owner_username=owner.username if owner else "Unknown",
                    my_role=collab.role,
                )
            )
    result.sort(key=lambda x: x.updated_at, reverse=True)
    return result


@router.post("/chats", response_model=ChatResponse)
def create_chat(
    chat: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_chat = Chat(user_id=current_user.id, title=chat.title)
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    return new_chat


@router.get("/chats/{chat_id}", response_model=ChatWithMessages)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_chat_with_access(chat_id, current_user, db)


@router.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")
    db.delete(chat)
    db.commit()
    return {"message": "Chat deleted successfully"}


@router.post("/chats/{chat_id}/messages", response_model=MessageResponse)
async def create_message(
    chat_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    await chat_lock_manager.acquire(
        chat_id, current_user.id, current_user.username, connection_manager
    )
    try:
        db.expire_all()
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        user_message = Message(chat_id=chat_id, role="user", content=message.content)
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        if chat.title == "New Conversation":
            message_count = db.query(Message).filter(Message.chat_id == chat_id).count()
            if message_count == 1:
                title = message.content[:50]
                if len(message.content) > 50:
                    title = title.rsplit(" ", 1)[0] + "..."
                chat.title = title
                db.commit()

        ai_message = generate_ai_response(
            chat_id, message.content, user_message, current_user.id, current_user.username, db
        )
        ws_state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
        await connection_manager.broadcast_to_chat(
            chat_id,
            {
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
                        "created_at": user_message.created_at.isoformat(),
                    },
                    {
                        "id": ai_message.id,
                        "chat_id": chat_id,
                        "role": "assistant",
                        "content": ai_message.content,
                        "workflow_data": ai_message.workflow_data,
                        "created_at": ai_message.created_at.isoformat(),
                    },
                ],
            },
            exclude_user=current_user.id,
        )
        return ai_message
    finally:
        await chat_lock_manager.release(chat_id, connection_manager)


@router.post("/chats/{chat_id}/messages/stream")
async def stream_message(
    chat_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    await chat_lock_manager.acquire(
        chat_id, current_user.id, current_user.username, connection_manager
    )

    db.expire_all()
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    user_message = Message(chat_id=chat_id, role="user", content=message.content)
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    if chat.title == "New Conversation":
        message_count = db.query(Message).filter(Message.chat_id == chat_id).count()
        if message_count == 1:
            title = message.content[:50]
            if len(message.content) > 50:
                title = title.rsplit(" ", 1)[0] + "..."
            chat.title = title
            db.commit()

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

            all_messages = (
                gen_db.query(Message)
                .filter(Message.chat_id == chat_id)
                .order_by(Message.created_at)
                .all()
            )
            last_workflow_msg = (
                gen_db.query(Message)
                .filter(
                    Message.chat_id == chat_id,
                    Message.role == "assistant",
                    Message.workflow_data.isnot(None),
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            conversation, workflow_context = build_conversation_history(
                all_messages, last_workflow_msg
            )
            system_msg = build_system_message(workflow_context)

            from openai import AsyncOpenAI
            from app.core.config import settings

            client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=120.0)
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[system_msg] + conversation,
                max_completion_tokens=5000,
                stream=True,
            )

            parser = IncrementalWorkflowParser()
            full_content = ""

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice or not choice.delta or not choice.delta.content:
                    continue
                token = choice.delta.content
                full_content += token
                yield f"event: text_chunk\ndata: {json.dumps({'content': token})}\n\n"
                new_nodes, new_edges = parser.feed(token)
                for node in new_nodes:
                    yield f"event: node_add\ndata: {json.dumps({'node': node})}\n\n"
                for edge in new_edges:
                    yield f"event: edge_add\ndata: {json.dumps({'edge': edge})}\n\n"

            if not full_content or not full_content.strip():
                prev_msg = (
                    gen_db.query(Message)
                    .filter(
                        Message.chat_id == chat_id,
                        Message.role == "assistant",
                        Message.workflow_data.isnot(None),
                    )
                    .order_by(Message.created_at.desc())
                    .first()
                )
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
                        if (
                            "nodes" not in parsed
                            or "edges" not in parsed
                            or len(parsed["nodes"]) == 0
                        ):
                            raise ValueError("Invalid workflow structure")
                        display_content = full_content.replace(full_match, "").strip()
                        display_content = re.sub(r"```\s*```", "", display_content).strip()
                        display_content = re.sub(r"\n\s*\n\s*\n+", "\n\n", display_content)
                        if not display_content or len(display_content) < 10:
                            display_content = "I've created a workflow visualization for you based on your requirements."
                    else:
                        if any(kw in msg_content_lower for kw in WORKFLOW_KEYWORDS):
                            workflow_data = json.dumps({
                                "nodes": [
                                    {"id": "1", "label": "Start", "type": "start"},
                                    {"id": "2", "label": "Process request", "type": "process"},
                                    {"id": "3", "label": "Complete", "type": "end"},
                                ],
                                "edges": [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}],
                            })
                            display_content = (
                                full_content.strip() if full_content.strip() else "I've created a basic workflow."
                            )
                except Exception:
                    workflow_data = None

            ai_message = Message(
                chat_id=chat_id,
                role="assistant",
                content=display_content,
                workflow_data=workflow_data,
            )
            gen_db.add(ai_message)
            gen_db.commit()
            gen_db.refresh(ai_message)
            if ai_message.workflow_data:
                ensure_workflow_state(chat_id, ai_message.workflow_data, user_id, gen_db)

            ws_state = (
                gen_db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
            )
            yield (
                f"event: workflow_complete\n"
                f"data: {json.dumps({'workflow_data': workflow_data, 'display_content': display_content})}\n\n"
            )
            yield (
                f"event: stream_end\n"
                f"data: {json.dumps({'message_id': ai_message.id, 'workflow_version': ws_state.version if ws_state else None})}\n\n"
            )

            await connection_manager.broadcast_to_chat(
                chat_id,
                {
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
                            "created_at": user_msg_created_at.isoformat(),
                        },
                        {
                            "id": ai_message.id,
                            "chat_id": chat_id,
                            "role": "assistant",
                            "content": ai_message.content,
                            "workflow_data": ai_message.workflow_data,
                            "created_at": ai_message.created_at.isoformat(),
                        },
                    ],
                },
                exclude_user=user_id,
            )
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            gen_db.close()
            await chat_lock_manager.release(chat_id, connection_manager)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/messages/{message_id}/workflow")
async def update_workflow(
    message_id: int,
    workflow_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    get_chat_with_access(msg.chat_id, current_user, db)
    new_data = workflow_data.get("workflow_data")
    msg.workflow_data = new_data
    db.commit()
    await connection_manager.broadcast_to_chat(
        msg.chat_id,
        {
            "type": "workflow_update",
            "chat_id": msg.chat_id,
            "message_id": message_id,
            "workflow_data": new_data,
            "updated_by": current_user.id,
            "updated_by_username": current_user.username,
        },
        exclude_user=current_user.id,
    )
    return {"message": "Workflow updated successfully"}
