"""
Disorder taxonomy (spec section 6) and Syndromes & Conditions (section 7).

Database-driven and extensible on purpose: an Admin can add new categories
and disorders without a code change. Nothing here claims to be an exhaustive
medical taxonomy.
"""
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class DisorderCategory(BaseModel):
    __tablename__ = "disorder_categories"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    disorders: Mapped[list["Disorder"]] = relationship("Disorder", back_populates="category")


class Disorder(BaseModel):
    __tablename__ = "disorders"

    category_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("disorder_categories.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    overview: Mapped[str] = mapped_column(Text, nullable=True)
    possible_characteristics: Mapped[str] = mapped_column(Text, nullable=True)
    speech_features: Mapped[str] = mapped_column(Text, nullable=True)
    assessment_notes: Mapped[str] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped["DisorderCategory"] = relationship("DisorderCategory", back_populates="disorders")


class Syndrome(BaseModel):
    """Syndromes & Conditions that MAY be associated with communication
    difficulties (spec section 7). The system must never infer a syndrome
    from an uploaded image/audio alone — this table is reference data only,
    never an automatic diagnostic output."""

    __tablename__ = "syndromes"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    communication_features: Mapped[str] = mapped_column(Text, nullable=True)
    potential_speech_features: Mapped[str] = mapped_column(Text, nullable=True)
    potential_language_features: Mapped[str] = mapped_column(Text, nullable=True)
    potential_voice_features: Mapped[str] = mapped_column(Text, nullable=True)
    assessment_considerations: Mapped[str] = mapped_column(Text, nullable=True)
    recommended_support_areas: Mapped[str] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
