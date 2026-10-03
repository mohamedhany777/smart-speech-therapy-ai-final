"""
Exercise system (spec section 36).
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class Exercise(BaseModel):
    __tablename__ = "exercises"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # fluency, pronunciation, ...
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    age_group: Mapped[str] = mapped_column(String(50), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=True)
    required_materials: Mapped[str] = mapped_column(Text, nullable=True)

    disorder_id: Mapped[str] = mapped_column(GUID(), ForeignKey("disorders.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ExerciseCompletion(BaseModel):
    __tablename__ = "exercise_completions"

    exercise_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=True)  # 0-100, nullable if not scoreable
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    exercise: Mapped["Exercise"] = relationship("Exercise")
