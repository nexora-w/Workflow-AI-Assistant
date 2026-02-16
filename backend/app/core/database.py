"""Database engine, session, and lifecycle."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Base


_db_url = settings.get_database_url()
_engine_kwargs = {}
if _db_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_add_current_version()


def _migrate_add_current_version() -> None:
    """Add current_version to workflow_states if missing (one-off migration)."""
    inspector = inspect(engine)
    if "workflow_states" not in inspector.get_table_names():
        return
    columns = [c["name"] for c in inspector.get_columns("workflow_states")]
    if "current_version" in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE workflow_states ADD COLUMN current_version INTEGER NOT NULL DEFAULT 1"
        ))
        conn.execute(text("UPDATE workflow_states SET current_version = version"))
