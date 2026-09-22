from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# NOTE: synchronous engine for MVP simplicity (SQLAlchemy 2.0 sync API is plenty for a
# personal-use tool's request volume). Swap for an async engine later if needed.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session, closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
