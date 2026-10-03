import uuid
from typing import Literal

from pydantic import BaseModel


class MediaFileOut(BaseModel):
    id: uuid.UUID
    media_type: str
    original_filename: str
    mime_type: str
    size_bytes: int
    duration_seconds: float | None
    model_config = {"from_attributes": True}


class AssessmentCreate(BaseModel):
    media_file_id: uuid.UUID
    assessment_type: Literal["audio", "image", "video"] = "audio"
    language: Literal["en", "ar"] = "en"
    # Optional target phrase/word for pronunciation analysis (spec section
    # 12). Only meaningful for assessment_type="audio" — silently ignored
    # otherwise, since image/video pipelines have no ASR-vs-reference step.
    reference_text: str | None = None


class AnalysisResultOut(BaseModel):
    id: uuid.UUID
    model_name: str
    model_version: str
    features_json: str
    input_quality_score: float | None
    limitations: str
    summary: str
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class AssessmentOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    media_file_id: uuid.UUID | None
    assessment_type: str
    language: str
    status: str
    review_status: str
    reviewer_notes: str | None
    analysis_result: AnalysisResultOut | None = None
    model_config = {"from_attributes": True}


class AssessmentReviewRequest(BaseModel):
    approve: bool
    notes: str | None = None
