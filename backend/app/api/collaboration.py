"""User search and chat collaboration endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Chat, ChatCollaborator
from app.schemas import CollaboratorAdd, CollaboratorResponse, UserSearchResponse
from app.services.chat import get_chat_with_access
from app.websocket import connection_manager

router = APIRouter(tags=["collaboration"])


@router.get("/users/search", response_model=List[UserSearchResponse])
def search_users(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(
            User.id != current_user.id,
            or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")),
        )
        .limit(10)
        .all()
    )
    return users


@router.post("/chats/{chat_id}/collaborators", response_model=CollaboratorResponse)
async def add_collaborator(
    chat_id: int,
    collab: CollaboratorAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")

    target_user = db.query(User).filter(User.username == collab.username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{collab.username}' not found")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a collaborator")

    existing = (
        db.query(ChatCollaborator)
        .filter(ChatCollaborator.chat_id == chat_id, ChatCollaborator.user_id == target_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="User is already a collaborator")

    new_collab = ChatCollaborator(
        chat_id=chat_id,
        user_id=target_user.id,
        role=collab.role,
        invited_by=current_user.id,
    )
    db.add(new_collab)
    db.commit()
    db.refresh(new_collab)

    await connection_manager.broadcast_to_chat(
        chat_id,
        {
            "type": "collaborator_added",
            "chat_id": chat_id,
            "user_id": target_user.id,
            "username": target_user.username,
            "role": collab.role,
        },
    )

    return CollaboratorResponse(
        id=new_collab.id,
        user_id=target_user.id,
        username=target_user.username,
        email=target_user.email,
        role=new_collab.role,
        invited_by=current_user.id,
        inviter_username=current_user.username,
        created_at=new_collab.created_at,
    )


@router.get("/chats/{chat_id}/collaborators", response_model=List[CollaboratorResponse])
def get_collaborators(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    collabs = db.query(ChatCollaborator).filter(ChatCollaborator.chat_id == chat_id).all()
    result = []
    for c in collabs:
        user = db.query(User).filter(User.id == c.user_id).first()
        inviter = db.query(User).filter(User.id == c.invited_by).first()
        if user:
            result.append(
                CollaboratorResponse(
                    id=c.id,
                    user_id=c.user_id,
                    username=user.username,
                    email=user.email,
                    role=c.role,
                    invited_by=c.invited_by,
                    inviter_username=inviter.username if inviter else "Unknown",
                    created_at=c.created_at,
                )
            )
    return result


@router.delete("/chats/{chat_id}/collaborators/{user_id}")
async def remove_collaborator(
    chat_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    is_owner = chat.user_id == current_user.id
    is_self = user_id == current_user.id
    if not is_owner and not is_self:
        raise HTTPException(status_code=403, detail="Only the owner can remove other collaborators")

    collab = (
        db.query(ChatCollaborator)
        .filter(ChatCollaborator.chat_id == chat_id, ChatCollaborator.user_id == user_id)
        .first()
    )
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    removed_user = db.query(User).filter(User.id == user_id).first()
    db.delete(collab)
    db.commit()

    await connection_manager.broadcast_to_chat(
        chat_id,
        {
            "type": "collaborator_removed",
            "chat_id": chat_id,
            "user_id": user_id,
            "username": removed_user.username if removed_user else "Unknown",
        },
    )
    return {"message": "Collaborator removed successfully"}


@router.patch("/chats/{chat_id}/collaborators/{user_id}")
def update_collaborator_role(
    chat_id: int,
    user_id: int,
    role_update: CollaboratorAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or you are not the owner")
    collab = (
        db.query(ChatCollaborator)
        .filter(ChatCollaborator.chat_id == chat_id, ChatCollaborator.user_id == user_id)
        .first()
    )
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    collab.role = role_update.role
    db.commit()
    return {"message": f"Role updated to {role_update.role}"}


@router.get("/chats/{chat_id}/online")
def get_online_users(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    return {"users": connection_manager.get_online_users(chat_id)}
