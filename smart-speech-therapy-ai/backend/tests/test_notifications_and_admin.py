import io

from tests.audio_fixture import make_wav_bytes
from tests.conftest import auth_headers, wait_for_assessment


def _upload_and_create_assessment(client, token) -> str:
    wav_bytes = make_wav_bytes(duration_seconds=1.5)
    upload_resp = client.post(
        "/api/v1/assessments/media/audio",
        files={"file": ("sample.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers=auth_headers(token),
    )
    media_id = upload_resp.json()["id"]
    create_resp = client.post(
        "/api/v1/assessments",
        json={"media_file_id": media_id, "assessment_type": "audio"},
        headers=auth_headers(token),
    )
    assessment_id = create_resp.json()["id"]
    wait_for_assessment(client, token, assessment_id)  # wait for the background task
    return assessment_id


def test_assessment_completion_creates_notification(client, user_token):
    _upload_and_create_assessment(client, user_token)

    notif_resp = client.get("/api/v1/notifications", headers=auth_headers(user_token))
    assert notif_resp.status_code == 200
    notifications = notif_resp.json()
    assert any(n["notification_type"] == "assessment_completed" for n in notifications)


def test_mark_notification_read(client, user_token):
    _upload_and_create_assessment(client, user_token)

    notifications = client.get("/api/v1/notifications", headers=auth_headers(user_token)).json()
    notif_id = notifications[0]["id"]
    assert notifications[0]["is_read"] is False

    read_resp = client.post(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers(user_token))
    assert read_resp.status_code == 200
    assert read_resp.json()["is_read"] is True


def test_user_cannot_read_others_notification(client, user_token):
    import uuid

    from tests.conftest import _create_user_with_role

    other_token = _create_user_with_role("USER", f"notifowner-{uuid.uuid4().hex}@example.com")
    _upload_and_create_assessment(client, other_token)

    other_notifs = client.get("/api/v1/notifications", headers=auth_headers(other_token)).json()
    notif_id = other_notifs[0]["id"]

    resp = client.post(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers(user_token))
    assert resp.status_code == 404


def test_admin_analytics_returns_real_counts(client, admin_token, user_token):
    before = client.get("/api/v1/admin/analytics", headers=auth_headers(admin_token)).json()

    _upload_and_create_assessment(client, user_token)

    after = client.get("/api/v1/admin/analytics", headers=auth_headers(admin_token)).json()
    assert after["total_assessments"] == before["total_assessments"] + 1
    assert after["completed_assessments"] == before["completed_assessments"] + 1


def test_regular_user_cannot_view_analytics_or_audit_logs(client, user_token):
    assert client.get("/api/v1/admin/analytics", headers=auth_headers(user_token)).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=auth_headers(user_token)).status_code == 403


def test_login_creates_audit_log_entry(client, admin_token):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "auditme@example.com", "password": "StrongPass123", "full_name": "Audit Me"},
    )
    assert resp.status_code == 201
    client.post("/api/v1/auth/login", json={"email": "auditme@example.com", "password": "StrongPass123"})

    logs_resp = client.get("/api/v1/admin/audit-logs", headers=auth_headers(admin_token))
    assert logs_resp.status_code == 200
    actions = [log["action"] for log in logs_resp.json()]
    assert "user.login" in actions
    assert "user.register" in actions
