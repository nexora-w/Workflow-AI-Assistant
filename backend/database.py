from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import sessionmaker, relationship, DeclarativeBase
from datetime import datetime
import enum
import os
from dotenv import load_dotenv

load_dotenv()

# Get DATABASE_URL from environment (Railway auto-provides this for PostgreSQL)
# For MySQL on Railway, you need to manually construct it from MYSQLHOST, MYSQLPORT, etc.
DATABASE_URL = os.getenv("DATABASE_URL")

# Debug logging for Railway
print("=" * 50)
print("DATABASE CONNECTION DEBUG:")
print(f"DATABASE_URL from env: {DATABASE_URL if DATABASE_URL else 'NOT SET'}")

if not DATABASE_URL:
    # Try to construct from Railway MySQL variables
    mysql_host = os.getenv("MYSQLHOST")
    mysql_port = os.getenv("MYSQLPORT", "3306")
    mysql_user = os.getenv("MYSQLUSER", "root")
    mysql_password = os.getenv("MYSQLPASSWORD", "")
    mysql_database = os.getenv("MYSQLDATABASE", "railway")
    
    print(f"MYSQLHOST: {mysql_host if mysql_host else 'NOT SET'}")
    print(f"MYSQLPORT: {mysql_port}")
    print(f"MYSQLUSER: {mysql_user}")
    print(f"MYSQLDATABASE: {mysql_database}")
    print(f"MYSQLPASSWORD: {'***' if mysql_password else 'NOT SET'}")
    
    if mysql_host:
        DATABASE_URL = f"mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        print(f"Constructed DATABASE_URL from MySQL vars")
    else:
        # Fallback to local development
        DATABASE_URL = "mysql+pymysql://root:password@localhost:3306/handbook_db"
        print("Using local development DATABASE_URL")

# Railway uses postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print("Converted postgres:// to postgresql://")

print(f"Final DATABASE_URL: {DATABASE_URL[:30]}... (truncated)")
print("=" * 50)

# Add check_same_thread=False for SQLite compatibility
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
class Base(DeclarativeBase):
    pass

class CollaboratorRole(str, enum.Enum):
    VIEWER = "viewer"
    EDITOR = "editor"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chats = relationship("Chat", back_populates="user")
    shared_chats = relationship("ChatCollaborator", back_populates="user", foreign_keys="ChatCollaborator.user_id")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    collaborators = relationship("ChatCollaborator", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    workflow_data = Column(Text, nullable=True)  # JSON string for workflow visualization
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="messages")

class WorkflowState(Base):
    """
    Single source of truth for the live workflow in a chat.
    
    - max_version: highest snapshot number (only incremented by real edits)
    - current_version: which snapshot is currently active (pointer)
    - Undo/redo move current_version without creating new snapshots.
    - A new real edit sets current_version = ++max_version and
      deletes any snapshots after the old current_version (git-style).
    """
    __tablename__ = "workflow_states"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), unique=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    current_version = Column(Integer, nullable=False, default=1)
    data = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    chat = relationship("Chat", backref="workflow_state_rel")
    editor = relationship("User", foreign_keys=[updated_by])


class WorkflowSnapshot(Base):
    """
    Immutable snapshot of the workflow at a specific version.
    Enables instant undo/redo/revert — just load the snapshot.
    """
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
    """
    Append-only log of every operation applied to a workflow.
    Useful for auditing, replaying, and debugging conflicts.
    """
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


class ChatCollaborator(Base):
    __tablename__ = "chat_collaborators"
    __table_args__ = (
        UniqueConstraint('chat_id', 'user_id', name='uq_chat_collaborator'),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default=CollaboratorRole.EDITOR.value)
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="collaborators")
    user = relationship("User", back_populates="shared_chats", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_add_current_version()


def _migrate_add_current_version():
    """Add current_version column to workflow_states if it doesn't exist yet."""
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(engine)
    if "workflow_states" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("workflow_states")]
    if "current_version" not in columns:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE workflow_states ADD COLUMN current_version INTEGER NOT NULL DEFAULT 1"
            ))
            conn.execute(text(
                "UPDATE workflow_states SET current_version = version"
            ))
