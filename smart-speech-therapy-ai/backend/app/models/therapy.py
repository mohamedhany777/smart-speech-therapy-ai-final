"""
Personalized support plans with human-in-the-loop review (spec sections
34-35, 94), plus system notifications (spec section 78).
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class TherapyPlan(BaseModel):
    __tablename__ = "therapy_plans"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), default="ai_draft", nullable=False)  # ai_draft|approved|rejected
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=True)
    sessions_per_week: Mapped[int] = mapped_column(Integer, nullable=True)
    goals: Mapped[str] = mapped_column(Text, nullable=True)

    reviewed_by_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, nullable=True)

    items: Mapped[list["TherapyPlanItem"]] = relationship(
        "TherapyPlanItem", back_populates="plan", cascade="all, delete-orphan"
    )


class TherapyPlanItem(BaseModel):
    __tablename__ = "therapy_plan_items"

    plan_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("therapy_plans.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)  # exercise | game
    exercise_id: Mapped[str] = mapped_column(GUID(), ForeignKey("exercises.id", ondelete="SET NULL"), nullable=True)
    game_id: Mapped[str] = mapped_column(GUID(), ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    frequency: Mapped[str] = mapped_column(String(100), nullable=True)  # e.g. "3x/week"
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    plan: Mapped["TherapyPlan"] = relationship("TherapyPlan", back_populates="items")


class Notification(BaseModel):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
