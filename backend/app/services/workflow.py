"""Workflow state and version/snapshot management."""

from sqlalchemy.orm import Session

from app.models import WorkflowState, WorkflowSnapshot, Message


def ensure_workflow_state(
    chat_id: int,
    data: str,
    user_id: int,
    db: Session,
    description: str = "AI-generated workflow",
) -> WorkflowState:
    """
    Create or update WorkflowState and save a snapshot.
    Truncate future snapshots if pointer was in the middle (git-style).
    """
    state = db.query(WorkflowState).filter(WorkflowState.chat_id == chat_id).first()
    if state:
        db.query(WorkflowSnapshot).filter(
            WorkflowSnapshot.chat_id == chat_id,
            WorkflowSnapshot.version > state.current_version,
        ).delete(synchronize_session=False)

        state.version += 1
        state.current_version = state.version
        state.data = data
        state.updated_by = user_id
    else:
        state = WorkflowState(
            chat_id=chat_id,
            version=1,
            current_version=1,
            data=data,
            updated_by=user_id,
        )
        db.add(state)
        db.flush()

    snapshot = WorkflowSnapshot(
        chat_id=chat_id,
        version=state.version,
        data=data,
        description=description,
        created_by=user_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(state)
    return state
