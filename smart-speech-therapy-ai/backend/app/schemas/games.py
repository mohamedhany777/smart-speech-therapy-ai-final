import uuid

from pydantic import BaseModel


class GameCreate(BaseModel):
    title: str
    slug: str
    game_type: str
    description: str | None = None
    difficulty: str = "beginner"
    language: str = "en"
    content_json: str  # JSON string; validated by the corresponding engine at play time


class GameOut(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    game_type: str
    description: str | None
    difficulty: str
    language: str
    is_active: bool
    model_config = {"from_attributes": True}


class GameSessionOut(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    status: str
    current_round: int
    total_rounds: int
    correct_count: int
    score: int
    model_config = {"from_attributes": True}


class GameAnswerSubmit(BaseModel):
    answer: str


class GameAnswerResult(BaseModel):
    correct: bool
    session_status: str
    score: int
    correct_count: int
    current_round: int
    total_rounds: int


class GameRoundPrompt(BaseModel):
    round_number: int
    total_rounds: int
    word: str | None = None
    options: list[str] | None = None
    prompt_text: str | None = None
    # New game types (spec section 7):
    words: list[str] | None = None  # sentence_builder: shuffled word tiles
    card_a: str | None = None  # memory_match: left card shown this round
    card_b: str | None = None  # memory_match: right card shown this round
    target_sound: str | None = None  # sound_hunt: the sound being listened for
    image_description: str | None = None  # picture_naming: what to name aloud


class GameAudioAnswerResult(GameAnswerResult):
    recognized_text: str | None = None
    asr_note: str = ""
