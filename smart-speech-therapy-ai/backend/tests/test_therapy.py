import io

from tests.audio_fixture import make_wav_bytes
from tests.conftest import auth_headers, wait_for_assessment


def _create_completed_assessment(client, user_token) -> str:
    wav_bytes = make_wav_bytes(duration_seconds=2.0)
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
    wait_for_assessment(client, user_token, assessment_id)
    return assessment_id


def test_generate_plan_creates_ai_draft_requiring_review(client, admin_token, user_token, specialist_token):
    # Seed an exercise so the plan has something to recommend
    client.post(
        "/api/v1/exercises",
        json={"title": "Fluency Warm-up", "category": "communication", "instructions": "Talk slowly."},
        headers=auth_headers(admin_token),
    )

    assessment_id = _create_completed_assessment(client, user_token)

    gen_resp = client.post(f"/api/v1/therapy-plans/generate/{assessment_id}", headers=auth_headers(user_token))
    assert gen_resp.status_code == 201
    plan = gen_resp.json()
    assert plan["status"] == "ai_draft"

    my_plans_resp = client.get("/api/v1/therapy-plans/me", headers=auth_headers(user_token))
    assert any(p["id"] == plan["id"] for p in my_plans_resp.json())

    pending_resp = client.get("/api/v1/therapy-plans/pending-review", headers=auth_headers(specialist_token))
    assert pending_resp.status_code == 200
    assert any(p["id"] == plan["id"] for p in pending_resp.json())

    review_resp = client.post(
        f"/api/v1/therapy-plans/{plan['id']}/review",
        json={"approve": True, "notes": "Approved with minor adjustments discussed in session."},
        headers=auth_headers(specialist_token),
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "approved"


def test_regular_user_cannot_review_plans(client, user_token):
    resp = client.get("/api/v1/therapy-plans/pending-review", headers=auth_headers(user_token))
    assert resp.status_code == 403


def test_other_user_cannot_generate_plan_for_someone_elses_assessment(client, user_token):
    import uuid

    from tests.conftest import _create_user_with_role

    assessment_id = _create_completed_assessment(client, user_token)
    other_token = _create_user_with_role("USER", f"intruder-{uuid.uuid4().hex}@example.com")

    resp = client.post(f"/api/v1/therapy-plans/generate/{assessment_id}", headers=auth_headers(other_token))
    assert resp.status_code == 403
