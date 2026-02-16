from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship, backref
from datetime import datetime

from .base import Base


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(
        Integer, ForeignKey("chats.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    version = Column(Integer, nullable=False, default=1)
    current_version = Column(Integer, nullable=False, default=1)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    chat = relationship(
        "Chat", backref=backref("workflow_state_rel", passive_deletes=True), passive_deletes=True
    )
    editor = relationship("User", foreign_keys=[updated_by])


class WorkflowSnapshot(Base):
    __tablename__ = "workflow_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    data = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by])


class WorkflowOperation(Base):
    __tablename__ = "workflow_operations"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    version_before = Column(Integer, nullable=False)
    version_after = Column(Integer, nullable=False)
    op_type = Column(String(50), nullable=False)
    op_data = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="applied")
    created_at = Column(DateTime, default=datetime.utcnow)
