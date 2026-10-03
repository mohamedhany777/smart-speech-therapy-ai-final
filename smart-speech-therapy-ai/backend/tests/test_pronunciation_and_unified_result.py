"""Tests for pronunciation analysis (spec section 12) and the Unified
Assessment Result structure (spec section 15)."""
import io
import time
import wave

from tests.conftest import auth_headers


def _tiny_wav_bytes(duration_s: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * duration_s))
    return buf.getvalue()


# --- pronunciation_analysis service (pure unit tests, no ASR dependency) ---
def test_pronunciation_exact_match():
    from app.services.pronunciation_analysis import analyze_pronunciation

    r = analyze_pronunciation("the cat sat down", "the cat sat down", asr_reliability=0.8)
    assert r.available is True
    assert r.accuracy == 1.0
    assert all(w.match for w in r.word_comparisons)
    assert all(w.mismatch_type == "match" for w in r.word_comparisons)


def test_pronunciation_substitution_and_omission():
    from app.services.pronunciation_analysis import analyze_pronunciation

    r = analyze_pronunciation("the cat sat down quietly", "the cat sad down", asr_reliability=0.8)
    assert r.available is True
    types = [w.mismatch_type for w in r.word_comparisons]
    assert "substitution" in types  # sat -> sad
    assert "omission" in types  # "quietly" never recognized
    assert 0 <= r.accuracy < 1.0


def test_pronunciation_no_reference_text():
    from app.services.pronunciation_analysis import analyze_pronunciation

    r = analyze_pronunciation("", "the cat sat down", asr_reliability=0.8)
    assert r.available is False
    assert r.accuracy is None


def test_pronunciation_no_speech_recognized():
    from app.services.pronunciation_analysis import analyze_pronunciation

    r = analyze_pronunciation("the cat sat down", "", asr_reliability=0.8)
    assert r.available is False
    assert r.reference_text == "the cat sat down"


def test_asr_reliability_ranking_is_honest_and_documented():
    from app.services.pronunciation_analysis import estimate_asr_reliability

    assert estimate_asr_reliability("hf-inference:openai/whisper-large-v3-turbo") > estimate_asr_reliability("whisper:openai/whisper-base")
    assert estimate_asr_reliability("whisper:openai/whisper-base") > estimate_asr_reliability("pocketsphinx")
    assert 0 <= estimate_asr_reliability("pocketsphinx") <= 1
    assert 0 <= estimate_asr_reliability("something-unknown") <= 1


# --- end-to-end through the API (uses PocketSphinx offline ASR fallback) ---
def _wait_for_assessment_result(client, token, assessment_id, timeout=20):
    h = auth_headers(token)
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/v1/assessments/{assessment_id}", headers=h)
        if r.json()["status"] not in ("pending", "processing"):
            return r.json()
        time.sleep(0.2)
    raise TimeoutError("assessment did not finish processing")


def test_create_assessment_with_reference_text_and_unified_result_shape(client, user_token):
    h = auth_headers(user_token)
    media = client.post(
        "/api/v1/assessments/media/audio",
        headers=h,
        files={"file": ("ref.wav", _tiny_wav_bytes(), "audio/wav")},
    ).json()
    created = client.post(
        "/api/v1/assessments",
        headers=h,
        json={"media_file_id": media["id"], "assessment_type": "audio", "reference_text": "hello world"},
    )
    assert created.status_code == 201
    aid = created.json()["id"]
    _wait_for_assessment_result(client, user_token, aid)

    r = client.get(f"/api/v1/assessments/{aid}/result", headers=h)
    assert r.status_code == 200
    body = r.json()

    # Exact unified shape from spec section 15.
    for field in (
        "assessment_id",
        "status",
        "input_quality",
        "transcription",
        "fluency",
        "stuttering",
        "pronunciation",
        "audio_features",
        "visual_observations",
        "evidence",
        "models",
        "limitations",
    ):
        assert field in body, f"missing unified-result field: {field}"

    assert body["assessment_id"] == aid
    assert body["visual_observations"] is None  # pure audio assessment: no visual evidence exists
    assert body["transcription"]["evidence_source"] == "audio"
    assert body["pronunciation"] is not None
    assert body["pronunciation"]["reference_text"] == "hello world"
    assert isinstance(body["models"], list) and len(body["models"]) >= 1
    assert isinstance(body["limitations"], list)


def test_unified_result_without_reference_text_has_no_pronunciation_claim(client, user_token):
    h = auth_headers(user_token)
    media = client.post(
        "/api/v1/assessments/media/audio",
        headers=h,
        files={"file": ("noref.wav", _tiny_wav_bytes(), "audio/wav")},
    ).json()
    created = client.post(
        "/api/v1/assessments", headers=h, json={"media_file_id": media["id"], "assessment_type": "audio"}
    )
    aid = created.json()["id"]
    _wait_for_assessment_result(client, user_token, aid)

    body = client.get(f"/api/v1/assessments/{aid}/result", headers=h).json()
    # No reference text supplied -> never fabricate a pronunciation claim.
    assert body["pronunciation"] is None


def test_unified_result_requires_ownership_or_review_permission(client, user_token, admin_token):
    h_user = auth_headers(user_token)
    media = client.post(
        "/api/v1/assessments/media/audio",
        headers=h_user,
        files={"file": ("owner.wav", _tiny_wav_bytes(), "audio/wav")},
    ).json()
    aid = client.post(
        "/api/v1/assessments", headers=h_user, json={"media_file_id": media["id"], "assessment_type": "audio"}
    ).json()["id"]

    # A different unrelated user cannot view it.
    from tests.conftest import _create_user_with_role

    other = _create_user_with_role("USER", "other-unified@test.com")
    assert client.get(f"/api/v1/assessments/{aid}/result", headers=auth_headers(other)).status_code == 403

    # Admin (has review_assessment permission) can.
    assert client.get(f"/api/v1/assessments/{aid}/result", headers=auth_headers(admin_token)).status_code == 200
