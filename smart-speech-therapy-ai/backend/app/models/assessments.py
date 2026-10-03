"""
Assessment engine models (spec sections 32-33): uploaded media, and the
structured analysis result produced from it.

`AnalysisResult` always records which model/pipeline version produced it
(spec section 52) and its limitations — the assessment engine
(app/services/assessment_service.py) is responsible for populating these
honestly, never inventing confidence scores it didn't compute.
"""
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class MediaFile(BaseModel):
    __tablename__ = "media_files"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)  # audio | image | video
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)


class Assessment(BaseModel):
    __tablename__ = "assessments"

    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    media_file_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True
    )
    assessment_type: Mapped[str] = mapped_column(String(50), nullable=False)  # audio | image | video | text | multimodal
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending|processing|completed|failed
    # Optional target phrase/word for pronunciation analysis (spec section
    # 12): "expected vs. recognized" comparison only runs when the user (or
    # an exercise) supplies what they were actually trying to say.
    reference_text: Mapped[str] = mapped_column(Text, nullable=True)

    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)  # unreviewed|approved|rejected
    reviewed_by_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, nullable=True)

    media_file: Mapped["MediaFile"] = relationship("MediaFile")
    analysis_result: Mapped["AnalysisResult"] = relationship(
        "AnalysisResult", back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )


class AnalysisResult(BaseModel):
    __tablename__ = "analysis_results"

    assessment_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # JSON-encoded structured features (MFCC summary stats, pitch, speaking
    # rate, pause metrics, etc.) — always real computed values, never
    # fabricated. See app/services/audio_analysis.py.
    features_json: Mapped[str] = mapped_column(Text, nullable=False)

    input_quality_score: Mapped[float] = mapped_column(Float, nullable=True)
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="analysis_result")
