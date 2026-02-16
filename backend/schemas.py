from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# Schema for when users are created
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
# Schwema for user login
class UserLogin(BaseModel):
    username: str
    password: str

# Schema for user response (excluding password)
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# Schema for token response
class Token(BaseModel):
    access_token: str
    token_type: str

# Schema for chat and message creation
class ChatCreate(BaseModel):
    title: str

# Schema for chat response
class ChatResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Schema for message creation
class MessageCreate(BaseModel):
    content: str

# Schema for message response
class MessageResponse(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    workflow_data: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Schema for chat with messages response view
class ChatWithMessages(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]
    
    class Config:
        from_attributes = True
