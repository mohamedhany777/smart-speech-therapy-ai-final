"""
Shared base class / mixins for all ORM models.

Every table gets:
- a UUID primary key (`id`)
- `created_at` / `updated_at` timestamps

This keeps individual model files focused on their own columns and
relationships, per the "modular, not one giant file" development
philosophy in the spec (section 129).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import GUID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class BaseModel(UUIDPKMixin, TimestampMixin, Base):
    """Abstract base combining UUID PK + timestamps. Import `Base` directly
    for models (like association tables) that shouldn't get these columns."""

    __abstract__ = True
