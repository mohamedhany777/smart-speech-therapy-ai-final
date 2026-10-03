"""
Role-Based Access Control models.

Design:
- `Role` (ADMIN / SPECIALIST / USER, extensible) has many `Permission`s.
- `User` has many `Role`s (many-to-many), so a user's effective permission
  set is the union of all their roles' permissions.
- Every sensitive API dependency checks permissions against this table at
  request time — never trusting frontend-hidden UI (spec section 4).
"""
from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import GUID
from app.models.base import BaseModel

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", GUID(), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", GUID(), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", GUID(), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(BaseModel):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[list["User"]] = relationship("User", secondary=user_roles, back_populates="roles")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class Permission(BaseModel):
    __tablename__ = "permissions"

    # e.g. "manage_knowledge_base", "review_assessment", "create_assessment"
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    roles: Mapped[list["Role"]] = relationship("Role", secondary=role_permissions, back_populates="permissions")

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


# --- Default role/permission catalogue (used by seed script) -----------------
# Kept here so seed data and the RBAC model live next to each other and can't
# drift apart.

DEFAULT_PERMISSIONS = {
    # Admin
    "manage_users": "Create, deactivate, and assign roles to users",
    "manage_knowledge_base": "Upload/manage KB documents, disorders, syndromes",
    "manage_models": "Configure AI models and pipelines",
    "manage_system_settings": "Change system-wide settings",
    "view_audit_logs": "View security/audit logs",
    "view_system_analytics": "View system-wide analytics",
    "manage_exercises": "Create/edit/deactivate exercises",
    "manage_games": "Create/edit/deactivate games",
    "manage_disorders": "Create/edit disorder taxonomy and syndromes",
    # Specialist
    "review_assessment": "Review AI assessments for assigned patients",
    "manage_therapy_plans": "Create/edit/approve/reject therapy plans",
    "view_assigned_patients": "View patients assigned to this specialist",
    # User
    "create_assessment": "Create a new self-assessment",
    "use_ai_assistant": "Use the AI assistant / RAG chat",
    "play_games": "Play gamified exercises",
    "complete_exercises": "Mark exercises as completed and record scores",
}

DEFAULT_ROLES = {
    "ADMIN": list(DEFAULT_PERMISSIONS.keys()),  # admins get everything
    "SPECIALIST": [
        "review_assessment",
        "manage_therapy_plans",
        "view_assigned_patients",
        "use_ai_assistant",
    ],
    "USER": [
        "create_assessment",
        "use_ai_assistant",
        "play_games",
        "complete_exercises",
    ],
}
