"""WebSocket connection and per-chat lock management."""

import asyncio
from typing import Dict

from fastapi import WebSocket


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

    async def broadcast_to_chat(self, chat_id: int, message: dict, exclude_user: int | None = None):
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
            "users": list(self.user_info[chat_id].values()),
        }
        await self.broadcast_to_chat(chat_id, presence_data)

    def get_online_users(self, chat_id: int) -> list:
        if chat_id in self.user_info:
            return list(self.user_info[chat_id].values())
        return []


class ChatLockManager:
    """One asyncio.Lock per chat_id so only one message is processed at a time per chat."""

    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._waiters: Dict[int, int] = {}

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
            self._waiters[chat_id] = 0
        return self._locks[chat_id]

    async def acquire(self, chat_id: int, user_id: int, username: str, manager: ConnectionManager):
        lock = self._get_lock(chat_id)
        self._waiters[chat_id] += 1

        if lock.locked():
            await manager.broadcast_to_chat(
                chat_id,
                {
                    "type": "processing",
                    "chat_id": chat_id,
                    "status": "queued",
                    "queued_by": user_id,
                    "queued_by_username": username,
                    "message": f"{username}'s request is waiting — another message is being processed",
                },
                exclude_user=None,
            )

        await lock.acquire()

        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "processing",
                "chat_id": chat_id,
                "status": "started",
                "processed_by": user_id,
                "processed_by_username": username,
                "message": f"Processing {username}'s message...",
            },
            exclude_user=user_id,
        )

    async def release(self, chat_id: int, manager: ConnectionManager):
        if chat_id in self._locks:
            self._waiters[chat_id] -= 1
            self._locks[chat_id].release()

            if self._waiters[chat_id] <= 0:
                del self._locks[chat_id]
                del self._waiters[chat_id]

        await manager.broadcast_to_chat(
            chat_id,
            {"type": "processing", "chat_id": chat_id, "status": "done"},
        )


connection_manager = ConnectionManager()
chat_lock_manager = ChatLockManager()
