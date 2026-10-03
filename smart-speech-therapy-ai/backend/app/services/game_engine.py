"""
Game engine (spec sections 37, 105, 106).

Server-authoritative: the client never sends a score, only an answer to the
current round. Score, correctness, and progression are all computed here.
Two real game types are implemented (extensible — add a new game_type by
implementing GameTypeEngine).
"""
import json
import random
import re
from abc import ABC, abstractmethod

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.games import Game, GameSession


class GameTypeEngine(ABC):
    """One implementation per Game.game_type."""

    @abstractmethod
    def build_round_order(self, content: dict) -> list[int]:
        """Return a shuffled list of round indices into content's item list."""

    @abstractmethod
    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        """Return the public (no-answer) prompt payload for a round."""

    @abstractmethod
    def check_answer(self, content: dict, round_index: int, answer: str) -> bool: ...


class WordMatchingEngine(GameTypeEngine):
    """content_json shape: {"pairs": [{"word": "...", "match": "..."}, ...]}
    Each round shows a word + 3 distractors; the player picks the correct match."""

    def build_round_order(self, content: dict) -> list[int]:
        order = list(range(len(content["pairs"])))
        random.shuffle(order)
        return order

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        pairs = content["pairs"]
        correct = pairs[round_index]
        distractor_pool = [p["match"] for i, p in enumerate(pairs) if i != round_index]
        distractors = random.sample(distractor_pool, k=min(3, len(distractor_pool)))
        options = distractors + [correct["match"]]
        random.shuffle(options)
        return {"word": correct["word"], "options": options}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        return content["pairs"][round_index]["match"].strip().lower() == answer.strip().lower()


class SoundRecognitionEngine(GameTypeEngine):
    """content_json shape: {"items": [{"prompt_text": "...", "correct_label": "..."}]}
    Text-based stand-in for an audio-prompt recognition game (the audio asset
    itself is a frontend/content concern; the engine only needs the label)."""

    def build_round_order(self, content: dict) -> list[int]:
        order = list(range(len(content["items"])))
        random.shuffle(order)
        return order

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        item = content["items"][round_index]
        return {"prompt_text": item["prompt_text"]}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        return content["items"][round_index]["correct_label"].strip().lower() == answer.strip().lower()


def _normalize_sentence(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", text.lower()))


class SentenceBuilderEngine(GameTypeEngine):
    """content_json shape:
    {"sentences": [{"words": ["The", "cat", "sat", "down"], "correct_sentence": "The cat sat down"}]}
    Each round shows the words in shuffled order; the player submits their
    attempted ordering as a single string (space-separated), which is
    compared to the correct sentence ignoring case/punctuation/extra
    whitespace — the point is testing word order and sentence construction,
    not exact punctuation."""

    def build_round_order(self, content: dict) -> list[int]:
        order = list(range(len(content["sentences"])))
        random.shuffle(order)
        return order

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        words = list(content["sentences"][round_index]["words"])
        shuffled = words[:]
        # Guarantee the shuffle actually scrambles the order (for >1 word)
        # so the round isn't accidentally already "solved".
        attempts = 0
        while shuffled == words and attempts < 10:
            random.shuffle(shuffled)
            attempts += 1
        return {"words": shuffled}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        correct = content["sentences"][round_index]["correct_sentence"]
        return _normalize_sentence(correct) == _normalize_sentence(answer)


class MemoryMatchEngine(GameTypeEngine):
    """content_json shape: {"pairs": [{"id": "1", "a": "Cat", "b": "🐱"}, ...]}
    Classic memory-match mechanic adapted to this engine's one-prompt/one-
    answer-per-round shape: each round reveals two cards (one 'a' side, one
    'b' side, possibly from different pairs) and the player judges whether
    they belong to the same pair ("match" / "no_match") — rather than a
    multiple-choice pick, this exercises recognition/recall the way a real
    memory-match game does."""

    def build_round_order(self, content: dict) -> list[int]:
        # One round per pair, but which cards are shown (matching or not) is
        # decided per-round in get_round_prompt/check_answer via a
        # deterministic-from-round_index coin flip, so build/get/check stay
        # consistent with each other without extra mutable state.
        order = list(range(len(content["pairs"])))
        random.shuffle(order)
        return order

    def _is_match_round(self, round_index: int) -> bool:
        # Alternate deterministically based on the pair's own index so a
        # given round_index always resolves the same way within one
        # session (get_round_prompt and check_answer are called separately
        # and must agree).
        return round_index % 2 == 0

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        pairs = content["pairs"]
        current = pairs[round_index]
        if self._is_match_round(round_index) or len(pairs) < 2:
            return {"card_a": current["a"], "card_b": current["b"]}
        others = [p for i, p in enumerate(pairs) if i != round_index]
        decoy = random.choice(others)
        return {"card_a": current["a"], "card_b": decoy["b"]}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        expected = "match" if self._is_match_round(round_index) or len(content["pairs"]) < 2 else "no_match"
        return answer.strip().lower() == expected


class SoundHuntEngine(GameTypeEngine):
    """content_json shape:
    {"target_sound": "s", "items": [{"word": "sun", "starts_with_target": true}, ...]}
    Each round shows one word; the player judges (yes/no) whether it starts
    with the session's target sound — a phonological-awareness task."""

    def build_round_order(self, content: dict) -> list[int]:
        order = list(range(len(content["items"])))
        random.shuffle(order)
        return order

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        return {"target_sound": content["target_sound"], "word": content["items"][round_index]["word"]}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        expected = "yes" if content["items"][round_index]["starts_with_target"] else "no"
        return answer.strip().lower() == expected


class PictureNamingEngine(GameTypeEngine):
    """content_json shape:
    {"items": [{"image_description": "A red apple", "target_word": "apple"}, ...]}
    The round prompt only ever exposes `image_description` — never
    `target_word` — since that would leak the answer to the client. Accepts
    a plain-text answer by default (check_answer below); the audio-based
    variant (say the word aloud, scored via real ASR) is a thin wrapper
    around this same check — see POST /games/sessions/{id}/answer-audio in
    api/v1/endpoints/games.py, which transcribes the recording first and
    then calls this same check_answer with the transcript."""

    def build_round_order(self, content: dict) -> list[int]:
        order = list(range(len(content["items"])))
        random.shuffle(order)
        return order

    def get_round_prompt(self, content: dict, round_index: int) -> dict:
        return {"image_description": content["items"][round_index]["image_description"]}

    def check_answer(self, content: dict, round_index: int, answer: str) -> bool:
        target = content["items"][round_index]["target_word"].strip().lower()
        spoken = answer.strip().lower()
        # Word-level match rather than strict full-string equality: ASR
        # transcripts of a single spoken word often include minor
        # filler/noise tokens ("uh apple") — any exact word match counts,
        # consistent with this being a screening/practice signal, not a
        # strict spelling test.
        return target in re.findall(r"[\w']+", spoken)


ENGINES: dict[str, GameTypeEngine] = {
    "word_matching": WordMatchingEngine(),
    "sound_recognition": SoundRecognitionEngine(),
    "sentence_builder": SentenceBuilderEngine(),
    "memory_match": MemoryMatchEngine(),
    "sound_hunt": SoundHuntEngine(),
    "picture_naming": PictureNamingEngine(),
}


def get_engine(game_type: str) -> GameTypeEngine:
    engine = ENGINES.get(game_type)
    if engine is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown game_type '{game_type}'"
        )
    return engine


def start_session(db: Session, game: Game, user_id: str) -> GameSession:
    content = json.loads(game.content_json)
    engine = get_engine(game.game_type)
    round_order = engine.build_round_order(content)

    session = GameSession(
        game_id=game.id,
        user_id=user_id,
        status="in_progress",
        current_round=0,
        total_rounds=len(round_order),
        correct_count=0,
        score=0,
        state_json=json.dumps({"round_order": round_order}),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_prompt(db: Session, session: GameSession) -> dict:
    if session.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not in progress")

    game = db.get(Game, session.game_id)
    content = json.loads(game.content_json)
    state = json.loads(session.state_json)
    round_index = state["round_order"][session.current_round]

    engine = get_engine(game.game_type)
    prompt = engine.get_round_prompt(content, round_index)
    return {
        "round_number": session.current_round + 1,
        "total_rounds": session.total_rounds,
        **prompt,
    }


def submit_answer(db: Session, session: GameSession, answer: str) -> dict:
    if session.status != "in_progress":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not in progress")

    game = db.get(Game, session.game_id)
    content = json.loads(game.content_json)
    state = json.loads(session.state_json)
    round_index = state["round_order"][session.current_round]

    engine = get_engine(game.game_type)
    is_correct = engine.check_answer(content, round_index, answer)

    if is_correct:
        session.correct_count += 1
        session.score += 10

    session.current_round += 1
    finished = session.current_round >= session.total_rounds
    session.status = "completed" if finished else "in_progress"

    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "correct": is_correct,
        "session_status": session.status,
        "score": session.score,
        "correct_count": session.correct_count,
        "current_round": session.current_round,
        "total_rounds": session.total_rounds,
    }
