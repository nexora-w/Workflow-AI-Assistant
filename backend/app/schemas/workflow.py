from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel


class WorkflowOp(BaseModel):
    op_type: Literal[
        "move_node", "add_node", "delete_node",
        "update_node", "add_edge", "delete_edge",
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
    version: int
    max_version: int
    data: str
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None


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
