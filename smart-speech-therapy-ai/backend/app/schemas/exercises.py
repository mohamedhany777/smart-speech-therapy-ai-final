import uuid

from pydantic import BaseModel


class ExerciseCreate(BaseModel):
    title: str
    category: str
    difficulty: str = "beginner"
    age_group: str | None = None
    language: str = "en"
    instructions: str
    duration_minutes: int | None = None
    goal: str | None = None
    required_materials: str | None = None
    disorder_id: uuid.UUID | None = None


class ExerciseUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    difficulty: str | None = None
    age_group: str | None = None
    language: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = None
    goal: str | None = None
    required_materials: str | None = None
    disorder_id: uuid.UUID | None = None
    is_active: bool | None = None


class ExerciseOut(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    difficulty: str
    age_group: str | None
    language: str
    instructions: str
    duration_minutes: int | None
    goal: str | None
    required_materials: str | None
    disorder_id: uuid.UUID | None
    is_active: bool
    model_config = {"from_attributes": True}


class ExerciseCompletionCreate(BaseModel):
    score: int | None = None
    notes: str | None = None


class ExerciseCompletionOut(BaseModel):
    id: uuid.UUID
    exercise_id: uuid.UUID
    user_id: uuid.UUID
    score: int | None
    notes: str | None
    model_config = {"from_attributes": True}
