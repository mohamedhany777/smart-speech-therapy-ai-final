"""
Domain profile tables that extend a User with role-specific data.

Kept separate from `User` (auth) so we're not mixing authentication concerns
with clinical/domain concerns — and so future profile fields don't force
migrations on the core auth table.
"""
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class PatientProfile(BaseModel):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    age_group: Mapped[str] = mapped_column(String(50), nullable=True)  # e.g. "child", "adolescent", "adult"
    goals: Mapped[str] = mapped_column(Text, nullable=True)
    assigned_specialist_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("specialist_profiles.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    assigned_specialist: Mapped["SpecialistProfile"] = relationship(
        "SpecialistProfile", back_populates="patients"
    )


class SpecialistProfile(BaseModel):
    __tablename__ = "specialist_profiles"

    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    license_number: Mapped[str] = mapped_column(String(100), nullable=True)
    specialization: Mapped[str] = mapped_column(String(255), nullable=True)
    bio: Mapped[str] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    patients: Mapped[list["PatientProfile"]] = relationship(
        "PatientProfile", back_populates="assigned_specialist", foreign_keys=[PatientProfile.assigned_specialist_id]
    )


from app.models.user import User  # noqa: E402
