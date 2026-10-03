"""
Auth support tables: refresh token storage and security audit log.

Refresh tokens are stored (hashed) so they can be revoked individually
(logout, "log out all devices", password reset) rather than relying purely
on JWT expiry.
"""
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class RefreshToken(BaseModel):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class AuditLog(BaseModel):
    """Records security-sensitive events (spec section 67): login, role
    changes, admin actions, document upload/delete, model changes, etc."""

    __tablename__ = "audit_logs"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. "login", "role.assign"
    resource_type: Mapped[str] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)  # JSON-encoded extra context


from app.models.user import User  # noqa: E402
