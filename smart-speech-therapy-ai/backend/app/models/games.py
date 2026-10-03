"""
Gamification models (spec sections 37, 105, 106).

`Game` holds static config (words/questions as JSON), `GameSession` tracks
one play-through with real state transitions enforced by
app/services/game_engine.py — no fake scoring, no shortcutting to a finished
state.
"""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import GUID
from app.models.base import BaseModel


class Game(BaseModel):
    __tablename__ = "games"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)  # word_matching | sound_recognition | ...
    description: Mapped[str] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # JSON-encoded content: word lists, question banks, etc. Structure is
    # game_type-specific; validated by the corresponding engine class.
    content_json: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GameSession(BaseModel):
    __tablename__ = "game_sessions"

    game_id: Mapped[str] = mapped_column(GUID(), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), default="in_progress", nullable=False)  # in_progress|completed|abandoned
    current_round: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # JSON-encoded remaining round order / per-round answers, so a session
    # can resume correctly and can't be replayed to inflate score.
    state_json: Mapped[str] = mapped_column(Text, nullable=False)

    game: Mapped["Game"] = relationship("Game")
