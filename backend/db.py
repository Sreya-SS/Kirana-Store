"""Database access layer.

All SQLite/SQLAlchemy specifics live here so the rest of the app only talks to
`SessionLocal` / `get_db`. To move to PostgreSQL later, change DATABASE_URL (and
drop the SQLite-only connect_args) -- no other file needs to change.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# SQLite file lives next to this backend package.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("KIRANAIQ_DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'kiranaiq.db')}")

# check_same_thread is a SQLite-only flag (APScheduler + request threads share the engine).
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    # Import models so they register on Base.metadata before create_all.
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
