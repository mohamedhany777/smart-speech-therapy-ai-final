"""
User account model.

Note: clinical profile data (patient goals, specialist assignments, etc.)
intentionally lives in separate `Patient` / `Specialist` profile tables
(app/models/profiles.py), not on User itself — keeps auth concerns separate
from domain concerns.
"""
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.rbac import user_roles


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)  # "en" | "ar"

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    roles: Mapped[list["Role"]] = relationship("Role", secondary=user_roles, back_populates="users")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )

    def has_permission(self, code: str) -> bool:
        return any(p.code == code for role in self.roles for p in role.permissions)

    def has_role(self, role_name: str) -> bool:
        return any(r.name == role_name for r in self.roles)

    def __repr__(self) -> str:
        return f"<User {self.email}>"


from app.models.rbac import Role  # noqa: E402  (avoid circular import at module load)
