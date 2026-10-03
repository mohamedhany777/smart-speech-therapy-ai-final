import io

from tests.audio_fixture import make_wav_bytes
from tests.conftest import auth_headers, wait_for_assessment


def test_full_audio_assessment_flow(client, user_token, specialist_token):
    wav_bytes = make_wav_bytes(duration_seconds=2.0)
    upload_resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers=auth_headers(user_token),
    )
    assert upload_resp.status_code == 201
    media = upload_resp.json()
    assert media["media_type"] == "audio"
    assert media["size_bytes"] == len(wav_bytes)

    create_resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media["id"], "assessment_type": "audio", "language": "en"},
        headers=auth_headers(user_token),
    )
    assert create_resp.status_code == 201
    # Processing now happens in a background task (see assessment_service's
    # load-handling design) — the initial response is "pending"/"processing",
    # not "completed" yet.
    assert create_resp.json()["status"] in ("pending", "processing")
    assessment = wait_for_assessment(client, user_token, create_resp.json()["id"])
    assert assessment["status"] == "completed"

    result = assessment["analysis_result"]
    assert result is not None
    assert result["model_name"] == "librosa-acoustic-features"
    # These must be REAL computed values, not placeholders.
    import json as jsonlib

    features = jsonlib.loads(result["features_json"])
    assert features["duration_seconds"] > 1.5
    assert features["sample_rate"] == 16000
    assert "fluency_indicators" in features
    assert "repetition_candidate_count" in features["fluency_indicators"]
    assert "does not diagnose" in result["summary"].lower()  # safety disclaimer present
    assert "you have" not in result["summary"].lower()  # never phrased as a diagnostic claim
    assert "screening" in result["summary"].lower() or "professional" in result["summary"].lower()

    # Owner can view their own assessment
    get_resp = client.get(f"/api/v1/assessments/{assessment['id']}", headers=auth_headers(user_token))
    assert get_resp.status_code == 200

    # Evidence panel returns something structured (may be empty if KB is empty)
    evidence_resp = client.get(
        f"/api/v1/assessments/{assessment['id']}/evidence", headers=auth_headers(user_token)
    )
    assert evidence_resp.status_code == 200
    assert "excerpts" in evidence_resp.json()

    # Specialist can review
    review_resp = client.post(
        f"/api/v1/assessments/{assessment['id']}/review",
        json={"approve": True, "notes": "Looks reasonable, recommend follow-up."},
        headers=auth_headers(specialist_token),
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["review_status"] == "approved"


def test_user_cannot_view_others_assessment(client, user_token):
    import uuid

    wav_bytes = make_wav_bytes(duration_seconds=1.0)
    upload_resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers=auth_headers(user_token),
    )
    media_id = upload_resp.json()["id"]

    create_resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media_id, "assessment_type": "audio"},
        headers=auth_headers(user_token),
    )
    assessment_id = create_resp.json()["id"]

    from tests.conftest import _create_user_with_role

    other_token = _create_user_with_role("USER", f"other-{uuid.uuid4().hex}@example.com")
    resp = client.get(f"/api/v1/assessments/{assessment_id}", headers=auth_headers(other_token))
    assert resp.status_code == 403


def test_unsupported_audio_extension_rejected(client, user_token):
    resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.txt", io.BytesIO(b"not audio"), "text/plain")},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 400


def test_cannot_create_assessment_with_someone_elses_media(client, user_token):
    import uuid

    from tests.conftest import _create_user_with_role

    other_token = _create_user_with_role("USER", f"owner-{uuid.uuid4().hex}@example.com")
    wav_bytes = make_wav_bytes(duration_seconds=1.0)
    upload_resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers=auth_headers(other_token),
    )
    media_id = upload_resp.json()["id"]

    resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media_id, "assessment_type": "audio"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 404
