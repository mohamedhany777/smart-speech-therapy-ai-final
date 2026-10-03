from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.games import Game, GameSession
from app.models.user import User
from app.schemas.games import (
    GameAnswerResult,
    GameAnswerSubmit,
    GameAudioAnswerResult,
    GameCreate,
    GameOut,
    GameRoundPrompt,
    GameSessionOut,
)
from app.security.dependencies import get_current_active_user, require_permission
from app.services import game_engine
from app.services.audio_analysis import get_speech_to_text_model
from app.services.storage import ALLOWED_AUDIO_EXTENSIONS, validate_upload

router = APIRouter(prefix="/games", tags=["Games"])


@router.get("", response_model=list[GameOut])
def list_games(db: Session = Depends(get_db)):
    return db.scalars(select(Game).where(Game.is_active.is_(True))).all()


@router.post("", response_model=GameOut, status_code=201)
def create_game(
    data: GameCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_permission("manage_games")),
):
    game = Game(**data.model_dump())
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _get_owned_session(db: Session, session_id: str, user: User) -> GameSession:
    session = db.get(GameSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game session not found")
    if str(session.user_id) != str(user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your game session")
    return session


@router.post("/{game_id}/start", response_model=GameSessionOut, status_code=201)
def start_game(
    game_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not current_user.has_permission("play_games"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permission: play_games")

    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    return game_engine.start_session(db, game, current_user.id)


@router.get("/sessions/{session_id}/round", response_model=GameRoundPrompt)
def get_round(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = _get_owned_session(db, session_id, current_user)
    return game_engine.get_current_prompt(db, session)


@router.post("/sessions/{session_id}/answer", response_model=GameAnswerResult)
def answer_round(
    session_id: str,
    data: GameAnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = _get_owned_session(db, session_id, current_user)
    return game_engine.submit_answer(db, session, data.answer)


@router.post("/sessions/{session_id}/answer-audio", response_model=GameAudioAnswerResult)
async def answer_round_audio(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    file: UploadFile = File(...),
):
    """Speech-based answer (spec section 7: Picture Naming, said aloud
    rather than typed): transcribe the recording with the platform's real
    ASR pipeline (see audio_analysis.py — same backend used for
    assessments, honestly subject to the same accuracy limitations, not a
    separate higher-confidence path), then score it exactly like a typed
    answer via the same server-authoritative game_engine.submit_answer."""
    session = _get_owned_session(db, session_id, current_user)
    content = await file.read()
    validate_upload(file, ALLOWED_AUDIO_EXTENSIONS, content)

    import os
    import tempfile

    suffix = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        stt_model = get_speech_to_text_model()
        transcription = stt_model.transcribe(tmp_path, language="en")
    finally:
        os.unlink(tmp_path)

    recognized_text = transcription.get("text") or ""
    result = game_engine.submit_answer(db, session, recognized_text)
    return {
        **result,
        "recognized_text": recognized_text if transcription.get("available") else None,
        "asr_note": transcription.get("note", ""),
    }
