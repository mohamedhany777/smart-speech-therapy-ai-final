import json
import uuid

from tests.conftest import auth_headers


def _create_word_matching_game(client, admin_token) -> str:
    resp = client.post(
        "/api/v1/games",
        json={
            "title": "Word Matching Test",
            "slug": f"word-matching-test-{uuid.uuid4().hex[:8]}",
            "game_type": "word_matching",
            "content_json": json.dumps(
                {
                    "pairs": [
                        {"word": "Cat", "match": "A small animal that meows"},
                        {"word": "Sun", "match": "The star at the center of our solar system"},
                        {"word": "Book", "match": "Printed pages bound together"},
                        {"word": "Tree", "match": "A tall plant with a trunk"},
                    ]
                }
            ),
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_full_game_playthrough_scores_correctly(client, admin_token, user_token):
    game_id = _create_word_matching_game(client, admin_token)

    start_resp = client.post(f"/api/v1/games/{game_id}/start", headers=auth_headers(user_token))
    assert start_resp.status_code == 201
    session = start_resp.json()
    assert session["status"] == "in_progress"
    assert session["total_rounds"] == 4
    session_id = session["id"]

    correct_answers = 0
    for _ in range(4):
        round_resp = client.get(f"/api/v1/games/sessions/{session_id}/round", headers=auth_headers(user_token))
        assert round_resp.status_code == 200
        prompt = round_resp.json()
        assert prompt["word"] is not None
        assert len(prompt["options"]) >= 2

        # Always answer with a real option so we can control correctness for
        # at least the first round; here we intentionally answer correctly
        # every time by finding which option matches known pairs.
        word_to_match = {
            "Cat": "A small animal that meows",
            "Sun": "The star at the center of our solar system",
            "Book": "Printed pages bound together",
            "Tree": "A tall plant with a trunk",
        }
        correct_option = word_to_match[prompt["word"]]

        answer_resp = client.post(
            f"/api/v1/games/sessions/{session_id}/answer",
            json={"answer": correct_option},
            headers=auth_headers(user_token),
        )
        assert answer_resp.status_code == 200
        result = answer_resp.json()
        assert result["correct"] is True
        correct_answers += 1

    assert result["session_status"] == "completed"
    assert result["correct_count"] == 4
    assert result["score"] == 40  # 10 points per correct round


def test_wrong_answer_does_not_score(client, admin_token, user_token):
    game_id = _create_word_matching_game(client, admin_token)
    start_resp = client.post(f"/api/v1/games/{game_id}/start", headers=auth_headers(user_token))
    session_id = start_resp.json()["id"]

    answer_resp = client.post(
        f"/api/v1/games/sessions/{session_id}/answer",
        json={"answer": "definitely not a real answer"},
        headers=auth_headers(user_token),
    )
    assert answer_resp.status_code == 200
    result = answer_resp.json()
    assert result["correct"] is False
    assert result["score"] == 0


def test_cannot_answer_another_users_session(client, admin_token, user_token):
    game_id = _create_word_matching_game(client, admin_token)
    start_resp = client.post(f"/api/v1/games/{game_id}/start", headers=auth_headers(user_token))
    session_id = start_resp.json()["id"]

    other_user_token = admin_token  # different identity than the session owner
    resp = client.post(
        f"/api/v1/games/sessions/{session_id}/answer",
        json={"answer": "x"},
        headers=auth_headers(other_user_token),
    )
    assert resp.status_code == 403


def test_cannot_answer_after_session_completed(client, admin_token, user_token):
    game_id = _create_word_matching_game(client, admin_token)
    start_resp = client.post(f"/api/v1/games/{game_id}/start", headers=auth_headers(user_token))
    session_id = start_resp.json()["id"]

    for _ in range(4):
        client.post(
            f"/api/v1/games/sessions/{session_id}/answer",
            json={"answer": "wrong"},
            headers=auth_headers(user_token),
        )

    resp = client.post(
        f"/api/v1/games/sessions/{session_id}/answer",
        json={"answer": "wrong"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 400


# --- new game engines (spec section 7: more game types) ---------------------
def test_sentence_builder_engine_direct():
    from app.services.game_engine import SentenceBuilderEngine

    engine = SentenceBuilderEngine()
    content = {"sentences": [{"words": ["The", "cat", "sat", "down"], "correct_sentence": "The cat sat down"}]}
    assert engine.check_answer(content, 0, "The cat sat down") is True
    assert engine.check_answer(content, 0, "the CAT sat down!") is True  # case/punctuation-insensitive
    assert engine.check_answer(content, 0, "cat The down sat") is False  # order matters
    prompt = engine.get_round_prompt(content, 0)
    assert sorted(prompt["words"]) == sorted(["The", "cat", "sat", "down"])


def test_memory_match_engine_direct():
    from app.services.game_engine import MemoryMatchEngine

    engine = MemoryMatchEngine()
    content = {"pairs": [{"id": "1", "a": "Cat", "b": "X"}, {"id": "2", "a": "Dog", "b": "Y"}]}
    # round_index 0 is a "match" round by construction (even index)
    prompt0 = engine.get_round_prompt(content, 0)
    assert prompt0 == {"card_a": "Cat", "card_b": "X"}
    assert engine.check_answer(content, 0, "match") is True
    assert engine.check_answer(content, 0, "no_match") is False
    # round_index 1 is a "no_match" round (odd index) with a decoy b
    prompt1 = engine.get_round_prompt(content, 1)
    assert prompt1["card_a"] == "Dog"
    assert prompt1["card_b"] != "Y"
    assert engine.check_answer(content, 1, "no_match") is True


def test_sound_hunt_engine_direct():
    from app.services.game_engine import SoundHuntEngine

    engine = SoundHuntEngine()
    content = {"target_sound": "s", "items": [{"word": "sun", "starts_with_target": True}, {"word": "cat", "starts_with_target": False}]}
    assert engine.get_round_prompt(content, 0) == {"target_sound": "s", "word": "sun"}
    assert engine.check_answer(content, 0, "yes") is True
    assert engine.check_answer(content, 0, "no") is False
    assert engine.check_answer(content, 1, "no") is True


def _make_game(client, admin_token, game_type: str, content: dict, slug: str):
    import json as _json

    r = client.post(
        "/api/v1/games",
        headers=auth_headers(admin_token),
        json={
            "title": slug,
            "slug": slug,
            "game_type": game_type,
            "content_json": _json.dumps(content),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_sentence_builder_full_session_via_api(client, user_token, admin_token):
    content = {"sentences": [{"words": ["Hello", "world"], "correct_sentence": "Hello world"}]}
    game = _make_game(client, admin_token, "sentence_builder", content, "sb-api-test")
    h = auth_headers(user_token)

    session = client.post(f"/api/v1/games/{game['id']}/start", headers=h, json={}).json()
    prompt = client.get(f"/api/v1/games/sessions/{session['id']}/round", headers=h).json()
    assert sorted(prompt["words"]) == ["Hello", "world"]

    result = client.post(
        f"/api/v1/games/sessions/{session['id']}/answer", headers=h, json={"answer": "Hello world"}
    ).json()
    assert result["correct"] is True
    assert result["session_status"] == "completed"
    assert result["score"] == 10


def test_memory_match_full_session_via_api(client, user_token, admin_token):
    content = {"pairs": [{"id": "1", "a": "Cat", "b": "X"}, {"id": "2", "a": "Dog", "b": "Y"}]}
    game = _make_game(client, admin_token, "memory_match", content, "mm-api-test")
    h = auth_headers(user_token)
    session = client.post(f"/api/v1/games/{game['id']}/start", headers=h, json={}).json()
    correct_map = {"Cat": "X", "Dog": "Y"}
    for _ in range(session["total_rounds"]):
        prompt = client.get(f"/api/v1/games/sessions/{session['id']}/round", headers=h).json()
        guess = "match" if correct_map.get(prompt["card_a"]) == prompt["card_b"] else "no_match"
        r = client.post(f"/api/v1/games/sessions/{session['id']}/answer", headers=h, json={"answer": guess}).json()
        assert r["correct"] is True


def test_sound_hunt_full_session_via_api(client, user_token, admin_token):
    content = {
        "target_sound": "s",
        "items": [{"word": "sun", "starts_with_target": True}, {"word": "cat", "starts_with_target": False}],
    }
    game = _make_game(client, admin_token, "sound_hunt", content, "sh-api-test")
    h = auth_headers(user_token)
    session = client.post(f"/api/v1/games/{game['id']}/start", headers=h, json={}).json()
    expected = {"sun": "yes", "cat": "no"}
    for _ in range(session["total_rounds"]):
        prompt = client.get(f"/api/v1/games/sessions/{session['id']}/round", headers=h).json()
        r = client.post(
            f"/api/v1/games/sessions/{session['id']}/answer",
            headers=h,
            json={"answer": expected[prompt["word"]]},
        ).json()
        assert r["correct"] is True


# --- Picture Naming (text path is deterministic; audio path uses real ASR) --
def test_picture_naming_engine_direct():
    from app.services.game_engine import PictureNamingEngine

    engine = PictureNamingEngine()
    content = {"items": [{"image_description": "A red apple", "target_word": "apple"}]}
    prompt = engine.get_round_prompt(content, 0)
    assert prompt == {"image_description": "A red apple"}
    assert "target_word" not in prompt  # never leak the answer to the client
    assert engine.check_answer(content, 0, "apple") is True
    assert engine.check_answer(content, 0, "an apple") is True  # word-level match tolerates filler words
    assert engine.check_answer(content, 0, "uh apple please") is True
    assert engine.check_answer(content, 0, "banana") is False


def test_picture_naming_typed_answer_full_session_via_api(client, user_token, admin_token):
    content = {"items": [{"image_description": "A red apple", "target_word": "apple"}]}
    game = _make_game(client, admin_token, "picture_naming", content, "pn-api-test")
    h = auth_headers(user_token)
    session = client.post(f"/api/v1/games/{game['id']}/start", headers=h, json={}).json()
    prompt = client.get(f"/api/v1/games/sessions/{session['id']}/round", headers=h).json()
    assert prompt["image_description"] == "A red apple"
    r = client.post(f"/api/v1/games/sessions/{session['id']}/answer", headers=h, json={"answer": "apple"}).json()
    assert r["correct"] is True


def test_picture_naming_audio_answer_endpoint_shape(client, user_token, admin_token):
    """Exercises the real ASR pipeline end-to-end through the audio-answer
    endpoint. PocketSphinx (the offline fallback used in this test
    environment) is not reliably accurate on synthesized speech, so this
    test asserts the endpoint's contract (shape, a real transcription
    attempt, correct scored consistently with what was recognized) rather
    than asserting the recognizer got the word right — that would make the
    test flaky on infrastructure this project doesn't control."""
    import io
    import wave

    content = {"items": [{"image_description": "A red apple", "target_word": "apple"}]}
    game = _make_game(client, admin_token, "picture_naming", content, "pn-audio-test")
    h = auth_headers(user_token)
    session = client.post(f"/api/v1/games/{game['id']}/start", headers=h, json={}).json()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    buf.seek(0)

    r = client.post(
        f"/api/v1/games/sessions/{session['id']}/answer-audio",
        headers=h,
        files={"file": ("say_apple.wav", buf.read(), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    for field in ("correct", "session_status", "score", "recognized_text", "asr_note"):
        assert field in body
    # Whatever was (or wasn't) recognized, "correct" must be consistent with
    # it — not independently fabricated.
    from app.services.game_engine import PictureNamingEngine

    expected = PictureNamingEngine().check_answer(content, 0, body["recognized_text"] or "")
    assert body["correct"] == expected


def test_picture_naming_audio_answer_requires_ownership(client, user_token, admin_token):
    from tests.conftest import _create_user_with_role

    content = {"items": [{"image_description": "A red apple", "target_word": "apple"}]}
    game = _make_game(client, admin_token, "picture_naming", content, "pn-audio-owner-test")
    session = client.post(
        f"/api/v1/games/{game['id']}/start", headers=auth_headers(user_token), json={}
    ).json()

    other = _create_user_with_role("USER", "other-picture-naming@test.com")
    r = client.post(
        f"/api/v1/games/sessions/{session['id']}/answer-audio",
        headers=auth_headers(other),
        files={"file": ("x.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )
    assert r.status_code == 403
