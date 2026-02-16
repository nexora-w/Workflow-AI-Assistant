"""WebSocket endpoint."""

from jose import JWTError, jwt

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import User, Chat, ChatCollaborator
from app.websocket import connection_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{chat_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(...),
):
    db = SessionLocal()
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
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
        is_collab = (
            db.query(ChatCollaborator)
            .filter(
                ChatCollaborator.chat_id == chat_id,
                ChatCollaborator.user_id == user.id,
            )
            .first()
        )
        if not is_owner and not is_collab:
            await websocket.close(code=4003, reason="Access denied")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return
    finally:
        db.close()

    await connection_manager.connect(websocket, chat_id, user.id, user.username)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.get("type") == "typing":
                await connection_manager.broadcast_to_chat(
                    chat_id,
                    {
                        "type": "typing",
                        "chat_id": chat_id,
                        "user_id": user.id,
                        "username": user.username,
                        "is_typing": data.get("is_typing", False),
                    },
                    exclude_user=user.id,
                )
    except WebSocketDisconnect:
        connection_manager.disconnect(chat_id, user.id)
        await connection_manager.broadcast_presence(chat_id)
    except Exception:
        connection_manager.disconnect(chat_id, user.id)
        await connection_manager.broadcast_presence(chat_id)
