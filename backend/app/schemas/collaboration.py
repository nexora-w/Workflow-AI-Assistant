from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class CollaboratorAdd(BaseModel):
    username: str
    role: Literal["viewer", "editor"] = "editor"


class CollaboratorResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    role: str
    invited_by: int
    inviter_username: str
    created_at: datetime


class SharedChatResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    owner_id: int
    owner_username: str
    my_role: str

    class Config:
        from_attributes = True


class UserSearchResponse(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True
