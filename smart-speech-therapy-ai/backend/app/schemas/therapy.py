import uuid

from pydantic import BaseModel


class TherapyPlanItemOut(BaseModel):
    id: uuid.UUID
    item_type: str
    exercise_id: uuid.UUID | None
    game_id: uuid.UUID | None
    frequency: str | None
    notes: str | None
    model_config = {"from_attributes": True}


class TherapyPlanOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    assessment_id: uuid.UUID | None
    status: str
    duration_weeks: int | None
    sessions_per_week: int | None
    goals: str | None
    reviewer_notes: str | None
    items: list[TherapyPlanItemOut] = []
    model_config = {"from_attributes": True}


class TherapyPlanReviewRequest(BaseModel):
    approve: bool
    notes: str | None = None


class NotificationOut(BaseModel):
    id: uuid.UUID
    notification_type: str
    title: str
    message: str
    is_read: bool
    model_config = {"from_attributes": True}
