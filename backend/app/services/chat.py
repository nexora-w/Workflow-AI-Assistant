"""Chat access control and helpers."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Chat, ChatCollaborator, User


def get_chat_with_access(
    chat_id: int,
    user: User,
    db: Session,
    require_role: str | None = None,
) -> Chat:
    """
    Return the chat if the user is the owner or a collaborator.
    If require_role is set, collaborators must have that role (e.g. 'editor').
    Raises 404 if chat doesn't exist or user has no access.
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.user_id == user.id:
        return chat

    collab = (
        db.query(ChatCollaborator)
        .filter(
            ChatCollaborator.chat_id == chat_id,
            ChatCollaborator.user_id == user.id,
        )
        .first()
    )

    if not collab:
        raise HTTPException(status_code=404, detail="Chat not found")

    if require_role and collab.role != require_role:
        raise HTTPException(
            status_code=403,
            detail=f"You need '{require_role}' access to perform this action",
        )

    return chat
