"""Workflow state, operations, versioning, and undo/revert endpoints."""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Message, WorkflowState, WorkflowSnapshot, WorkflowOperation
from app.schemas import (
    WorkflowOperationRequest,
    WorkflowOperationResponse,
    WorkflowStateResponse,
    VersionTimelineResponse,
    VersionEntry,
    RevertRequest,
    RevertResponse,
)
from app.services.chat import get_chat_with_access
from app.services.workflow import ensure_workflow_state
from app.websocket import connection_manager, chat_lock_manager
from app.utils import Operation, resolve_conflict

router = APIRouter(tags=["workflow"])


@router.get("/chats/{chat_id}/workflow/state", response_model=WorkflowStateResponse)
def get_workflow_state(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        last_workflow_msg = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        if not last_workflow_msg:
            raise HTTPException(status_code=404, detail="No workflow exists for this chat")
        state = ensure_workflow_state(
            chat_id, last_workflow_msg.workflow_data, current_user.id, db
        )
    return WorkflowStateResponse(
        chat_id=chat_id,
        version=state.current_version,
        max_version=state.version,
        data=state.data,
        updated_at=state.updated_at,
        updated_by=state.updated_by,
    )


@router.post("/chats/{chat_id}/workflow/operations", response_model=WorkflowOperationResponse)
async def apply_workflow_operations(
    chat_id: int,
    request: WorkflowOperationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        last_workflow_msg = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        if not last_workflow_msg:
            raise HTTPException(status_code=404, detail="No workflow exists for this chat")
        state = ensure_workflow_state(
            chat_id, last_workflow_msg.workflow_data, current_user.id, db
        )

    incoming_ops = [Operation(op_type=op.op_type, payload=op.payload) for op in request.operations]
    op_log = []
    if request.base_version < state.version:
        op_records = (
            db.query(WorkflowOperation)
            .filter(
                WorkflowOperation.chat_id == chat_id,
                WorkflowOperation.version_after > request.base_version,
                WorkflowOperation.version_after <= state.version,
                WorkflowOperation.status == "applied",
            )
            .order_by(WorkflowOperation.version_after.asc())
            .all()
        )
        op_log = [{"op_data": r.op_data} for r in op_records]

    result = resolve_conflict(
        current_data=state.data,
        current_version=state.version,
        base_version=request.base_version,
        incoming_ops=incoming_ops,
        op_log=op_log,
    )

    if result.status == "conflict":
        return WorkflowOperationResponse(
            status="conflict",
            version=state.current_version,
            data=state.data,
            conflicts=result.conflicts,
        )

    db.query(WorkflowSnapshot).filter(
        WorkflowSnapshot.chat_id == chat_id,
        WorkflowSnapshot.version > state.current_version,
    ).delete(synchronize_session=False)

    state.data = result.new_data
    state.version = result.new_version
    state.current_version = result.new_version
    state.updated_by = current_user.id

    op_desc = ", ".join(op.op_type for op in incoming_ops)
    op_record = WorkflowOperation(
        chat_id=chat_id,
        user_id=current_user.id,
        version_before=request.base_version,
        version_after=result.new_version,
        op_type=op_desc,
        op_data=json.dumps([{"op_type": op.op_type, "payload": op.payload} for op in incoming_ops]),
        status=result.status,
    )
    db.add(op_record)
    snapshot = WorkflowSnapshot(
        chat_id=chat_id,
        version=result.new_version,
        data=result.new_data,
        description=f"{current_user.username}: {op_desc}",
        created_by=current_user.id,
    )
    db.add(snapshot)

    last_msg = (
        db.query(Message)
        .filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_msg:
        last_msg.workflow_data = result.new_data
    db.commit()

    await connection_manager.broadcast_to_chat(
        chat_id,
        {
            "type": "workflow_op",
            "chat_id": chat_id,
            "version": result.new_version,
            "data": result.new_data,
            "operations": [{"op_type": op.op_type, "payload": op.payload} for op in incoming_ops],
            "applied_by": current_user.id,
            "applied_by_username": current_user.username,
            "status": result.status,
        },
        exclude_user=current_user.id,
    )

    return WorkflowOperationResponse(
        status=result.status,
        version=result.new_version,
        data=result.new_data,
        conflicts=[],
    )


@router.get("/chats/{chat_id}/workflows/history")
def get_workflow_history(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    messages = (
        db.query(Message)
        .filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .all()
    )
    return [
        {"id": msg.id, "workflow_data": msg.workflow_data, "created_at": msg.created_at}
        for msg in messages
    ]


@router.post("/chats/{chat_id}/workflows/undo")
async def undo_workflow(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    await chat_lock_manager.acquire(
        chat_id, current_user.id, current_user.username, connection_manager
    )
    try:
        db.expire_all()
        last_messages = (
            db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at.desc()).limit(2).all()
        )
        if len(last_messages) < 2:
            raise HTTPException(status_code=400, detail="No messages to undo")
        for msg in last_messages:
            db.delete(msg)
        db.commit()
        prev_workflow = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.workflow_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        result = {
            "message": "Undone successfully",
            "workflow_data": prev_workflow.workflow_data if prev_workflow else None,
        }
        await connection_manager.broadcast_to_chat(
            chat_id,
            {
                "type": "undo",
                "chat_id": chat_id,
                "undone_by": current_user.id,
                "undone_by_username": current_user.username,
                "workflow_data": result["workflow_data"],
            },
            exclude_user=current_user.id,
        )
        return result
    finally:
        await chat_lock_manager.release(chat_id, connection_manager)


@router.get("/chats/{chat_id}/workflow/versions", response_model=VersionTimelineResponse)
def get_version_timeline(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    cur_ver = state.current_version if state else 0
    snapshots = (
        db.query(WorkflowSnapshot)
        .filter(WorkflowSnapshot.chat_id == chat_id)
        .order_by(WorkflowSnapshot.version.asc())
        .all()
    )
    entries: List[VersionEntry] = []
    for snap in snapshots:
        creator = db.query(User).filter(User.id == snap.created_by).first() if snap.created_by else None
        entries.append(
            VersionEntry(
                version=snap.version,
                description=snap.description,
                created_by=snap.created_by,
                created_by_username=creator.username if creator else None,
                created_at=snap.created_at,
                is_current=(snap.version == cur_ver),
            )
        )
    return VersionTimelineResponse(chat_id=chat_id, current_version=cur_ver, versions=entries)


@router.post("/chats/{chat_id}/workflow/revert", response_model=RevertResponse)
async def revert_to_version(
    chat_id: int,
    request: RevertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    snapshot = (
        db.query(WorkflowSnapshot)
        .filter(
            WorkflowSnapshot.chat_id == chat_id,
            WorkflowSnapshot.version == request.target_version,
        )
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Version {request.target_version} not found")
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if not state:
        raise HTTPException(status_code=404, detail="No workflow state found")

    state.current_version = request.target_version
    state.data = snapshot.data
    state.updated_by = current_user.id
    last_msg = (
        db.query(Message)
        .filter(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.workflow_data.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_msg:
        last_msg.workflow_data = snapshot.data
    db.commit()

    await connection_manager.broadcast_to_chat(
        chat_id,
        {
            "type": "version_revert",
            "chat_id": chat_id,
            "current_version": state.current_version,
            "max_version": state.version,
            "target_version": request.target_version,
            "data": snapshot.data,
            "reverted_by": current_user.id,
            "reverted_by_username": current_user.username,
        },
        exclude_user=current_user.id,
    )
    return RevertResponse(
        version=state.current_version,
        data=snapshot.data,
        message=f"Moved to version {request.target_version}",
    )


@router.get("/chats/{chat_id}/workflow/versions/{version}")
def get_version_snapshot(
    chat_id: int,
    version: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_chat_with_access(chat_id, current_user, db)
    snapshot = (
        db.query(WorkflowSnapshot)
        .filter(
            WorkflowSnapshot.chat_id == chat_id,
            WorkflowSnapshot.version == version,
        )
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    creator = db.query(User).filter(User.id == snapshot.created_by).first() if snapshot.created_by else None
    return {
        "version": snapshot.version,
        "data": snapshot.data,
        "description": snapshot.description,
        "created_by_username": creator.username if creator else None,
        "created_at": snapshot.created_at.isoformat(),
    }
