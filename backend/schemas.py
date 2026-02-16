from pydantic import BaseModel, EmailStr
from typing import Optional, List, Literal
from datetime import datetime

# Schema for when users are created
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
# Schema for user login
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

# --- Collaboration Schemas ---

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

# --- Workflow Operation Schemas ---

class WorkflowOp(BaseModel):
    op_type: Literal[
        "move_node", "add_node", "delete_node",
        "update_node", "add_edge", "delete_edge"
    ]
    payload: dict

class WorkflowOperationRequest(BaseModel):
    base_version: int
    operations: List[WorkflowOp]

class WorkflowOperationResponse(BaseModel):
    status: Literal["applied", "merged", "conflict"]
    version: int
    data: str
    conflicts: List[str] = []

class WorkflowStateResponse(BaseModel):
    chat_id: int
    version: int          # current_version pointer (where you are)
    max_version: int      # highest snapshot number
    data: str
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None

# --- Version Control Schemas ---

class VersionEntry(BaseModel):
    version: int
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_by_username: Optional[str] = None
    created_at: datetime
    is_current: bool = False

class VersionTimelineResponse(BaseModel):
    chat_id: int
    current_version: int
    versions: List[VersionEntry]

class RevertRequest(BaseModel):
    target_version: int

class RevertResponse(BaseModel):
    version: int
    data: str
    message: str

# --- WebSocket Event Schemas ---

class WSEvent(BaseModel):
    type: str
    chat_id: int
    data: dict
