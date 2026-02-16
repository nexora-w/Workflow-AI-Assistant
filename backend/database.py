from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
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
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chats = relationship("Chat", back_populates="user")

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    workflow_data = Column(Text, nullable=True)  # JSON string for workflow visualization
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="messages")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
