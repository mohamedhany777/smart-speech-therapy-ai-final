import uuid

from pydantic import BaseModel


class DisorderCategoryCreate(BaseModel):
    name: str
    description: str | None = None


class DisorderCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DisorderCategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    model_config = {"from_attributes": True}


class DisorderCreate(BaseModel):
    name: str
    slug: str
    language: str = "en"
    category_id: uuid.UUID | None = None
    overview: str | None = None
    possible_characteristics: str | None = None
    speech_features: str | None = None
    assessment_notes: str | None = None


class DisorderUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    language: str | None = None
    category_id: uuid.UUID | None = None
    overview: str | None = None
    possible_characteristics: str | None = None
    speech_features: str | None = None
    assessment_notes: str | None = None
    is_active: bool | None = None


class DisorderOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    language: str
    category_id: uuid.UUID | None
    overview: str | None
    possible_characteristics: str | None
    speech_features: str | None
    assessment_notes: str | None
    is_active: bool
    model_config = {"from_attributes": True}


class SyndromeCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    communication_features: str | None = None
    potential_speech_features: str | None = None
    potential_language_features: str | None = None
    potential_voice_features: str | None = None
    assessment_considerations: str | None = None
    recommended_support_areas: str | None = None


class SyndromeUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    communication_features: str | None = None
    potential_speech_features: str | None = None
    potential_language_features: str | None = None
    potential_voice_features: str | None = None
    assessment_considerations: str | None = None
    recommended_support_areas: str | None = None
    is_active: bool | None = None


class SyndromeOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    communication_features: str | None
    potential_speech_features: str | None
    potential_language_features: str | None
    potential_voice_features: str | None
    assessment_considerations: str | None
    recommended_support_areas: str | None
    is_active: bool
    model_config = {"from_attributes": True}


class DisorderProfileDraft(BaseModel):
    """AI-drafted disorder profile fields extracted from an uploaded
    document — always returned for admin review/editing, never
    auto-saved."""

    suggested_name: str | None = None
    suggested_slug: str | None = None
    overview: str | None = None
    possible_characteristics: str | None = None
    speech_features: str | None = None
    assessment_notes: str | None = None
    available: bool
    note: str
