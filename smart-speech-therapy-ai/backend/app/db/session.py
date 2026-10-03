"""
SQLAlchemy engine + session management.

Works against PostgreSQL in production (per spec section 62) and transparently
falls back to SQLite for local development/testing when DATABASE_URL points
to a sqlite:/// URL — no code changes needed to switch.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session, rolling back on any
    unhandled exception (so a failed request never leaves an aborted
    transaction on a pooled/shared connection for the next request) and
    always closing the session afterward."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
