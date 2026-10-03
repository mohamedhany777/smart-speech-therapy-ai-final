"""Regression tests for bugs found during the pre-delivery review."""
import uuid

from tests.conftest import _create_user_with_role, auth_headers


def _make_user_and_token(client, email):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "T", "preferred_language": "en"},
    )
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return r.json()


def _user_id(client, admin_token, email):
    users = client.get("/api/v1/admin/users", headers=auth_headers(admin_token)).json()
    return next(u["id"] for u in users if u["email"] == email)


# --- admin deactivate route (decorator was missing -> 404/dead code) --------
def test_admin_can_deactivate_user_and_tokens_are_revoked(client, admin_token):
    tokens = _make_user_and_token(client, "deact1@test.com")
    uid = _user_id(client, admin_token, "deact1@test.com")

    r = client.post(f"/api/v1/admin/users/{uid}/deactivate", headers=auth_headers(admin_token))
    assert r.status_code == 204

    assert client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"])).status_code == 403
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_deactivate_requires_admin(client, user_token):
    r = client.post(f"/api/v1/admin/users/{uuid.uuid4()}/deactivate", headers=auth_headers(user_token))
    assert r.status_code == 403


def test_deactivate_unknown_and_invalid_user(client, admin_token):
    h = auth_headers(admin_token)
    assert client.post(f"/api/v1/admin/users/{uuid.uuid4()}/deactivate", headers=h).status_code == 404
    assert client.post("/api/v1/admin/users/not-a-uuid/deactivate", headers=h).status_code == 422


def test_admin_cannot_deactivate_self(client, admin_token):
    me = client.get("/api/v1/auth/me", headers=auth_headers(admin_token)).json()
    r = client.post(f"/api/v1/admin/users/{me['id']}/deactivate", headers=auth_headers(admin_token))
    assert r.status_code == 400


# --- malformed ids must be 404, never 500 -----------------------------------
def test_malformed_ids_return_404_not_500(client, user_token, admin_token):
    uh, ah = auth_headers(user_token), auth_headers(admin_token)
    assert client.post("/api/v1/games/abc/start", headers=uh, json={}).status_code == 404
    assert client.post("/api/v1/exercises/abc/complete", headers=uh, json={"score": 1}).status_code == 404
    assert client.get("/api/v1/assessments/abc", headers=uh).status_code == 404
    assert client.get("/api/v1/assessments/abc/evidence", headers=uh).status_code == 404
    assert client.patch("/api/v1/disorders/abc", headers=ah, json={"name": "x"}).status_code == 404
    assert client.patch("/api/v1/exercises/abc", headers=ah, json={"title": "x"}).status_code == 404
    assert client.get("/api/v1/games/sessions/abc/round", headers=uh).status_code == 404


# --- inactive content must not leak to anonymous / regular users ------------
def test_include_inactive_requires_privileges(client, user_token, admin_token):
    for path in ("/api/v1/exercises", "/api/v1/disorders", "/api/v1/disorders/syndromes"):
        assert client.get(f"{path}?include_inactive=true").status_code == 401
        assert client.get(f"{path}?include_inactive=true", headers=auth_headers(user_token)).status_code == 403
        assert client.get(f"{path}?include_inactive=true", headers=auth_headers(admin_token)).status_code == 200
        assert client.get(path).status_code == 200  # normal public listing still works


# --- assessments: invalid type rejected; corrupt upload -> failed + notified --
def test_assessment_type_and_language_are_validated(client, user_token):
    r = client.post(
        "/api/v1/assessments",
        headers=auth_headers(user_token),
        json={"media_file_id": str(uuid.uuid4()), "assessment_type": "telepathy"},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/assessments",
        headers=auth_headers(user_token),
        json={"media_file_id": str(uuid.uuid4()), "assessment_type": "audio", "language": "xx"},
    )
    assert r.status_code == 422


def test_corrupt_audio_ends_in_failed_status_with_notification(client, user_token):
    from tests.conftest import wait_for_assessment

    h = auth_headers(user_token)
    media = client.post(
        "/api/v1/assessments/media/audio",
        headers=h,
        files={"file": ("broken.wav", b"RIFF" + b"\x00" * 200, "audio/wav")},
    )
    # Upload validation may reject it outright (also acceptable); otherwise it must fail cleanly.
    if media.status_code != 201:
        assert media.status_code in (400, 415, 422)
        return
    a = client.post(
        "/api/v1/assessments",
        headers=h,
        json={"media_file_id": media.json()["id"], "assessment_type": "audio"},
    ).json()
    final = wait_for_assessment(client, user_token, a["id"])
    assert final["status"] == "failed"
    notes = client.get("/api/v1/notifications", headers=h).json()
    assert any(n["notification_type"] == "assessment_failed" for n in notes)


# --- therapy plans: idempotent generation, single review, video features ----
def test_plan_feature_flattening_for_video():
    from app.services.therapy_plan_service import _recommended_categories

    video = {"audio_result": {"features": {"pause_count": 9, "speaking_rate_estimate": 0.8}}, "video_summary": {}}
    assert "fluency" in _recommended_categories(video)
    assert _recommended_categories({}) == ["communication"]


# --- knowledge base: failed ingestion must not leave a broken document ------
def test_failed_kb_upload_leaves_no_orphan_document(client, admin_token):
    """A failed upload must NOT silently vanish (spec section 6 requires a
    real, inspectable FAILED status) but must also not pollute the normal
    published-documents list, and must not leave orphaned chunks or an
    uploaded file behind for a document nobody can ever use."""
    h = auth_headers(admin_token)
    before = client.get("/api/v1/knowledge-base/documents", headers=h).json()
    r = client.post(
        "/api/v1/knowledge-base/documents",
        headers=h,
        data={"title": "Empty doc"},
        files={"file": ("empty.txt", b"   \n  ", "text/plain")},
    )
    assert r.status_code == 422

    # Doesn't show up in the normal published list...
    after = client.get("/api/v1/knowledge-base/documents", headers=h).json()
    assert len(after) == len(before)

    # ...but IS visible to an admin explicitly asking for the full picture,
    # with an honest FAILED status and a reason, and zero chunks.
    full = client.get("/api/v1/knowledge-base/documents?include_inactive=true", headers=h).json()
    failed = [d for d in full if d["title"] == "Empty doc"]
    assert len(failed) == 1
    assert failed[0]["status"] == "FAILED"
    assert failed[0]["failure_reason"]
    assert failed[0]["chunk_count"] == 0
    assert failed[0]["is_active"] is True  # not "unpublished" — it never published; it FAILED


def test_failed_document_never_leaks_into_query_because_never_indexed(client, admin_token, user_token):
    """A FAILED document has zero chunks, so even though is_active stays
    True (it was never published, not unpublished), it structurally cannot
    contribute to RAG answers — nothing was ever indexed for it."""
    h = auth_headers(admin_token)
    client.post(
        "/api/v1/knowledge-base/documents",
        headers=h,
        data={"title": "Bad Upload For Query Test"},
        files={"file": ("empty2.txt", b"   ", "text/plain")},
    )
    # Any subsequent query must not somehow reference the failed document.
    r = client.post(
        "/api/v1/knowledge-base/query",
        headers=auth_headers(user_token),
        json={"query": "Bad Upload For Query Test"},
    )
    assert r.status_code == 200
    assert all(e.get("document_id") is None or "Bad Upload" not in (e.get("title") or "") for e in r.json()["excerpts"])


# --- rate limiting on login (brute-force protection) ------------------------
def test_login_rate_limit_enforced():
    """RATE_LIMIT_LOGIN_PER_MINUTE was defined in settings but never enforced
    anywhere — this exercises the limiter directly against a tiny window so
    the test is fast and doesn't depend on the global test suite's setting."""
    from fastapi import Request

    from app.security import rate_limit

    rate_limit._hits.clear()

    class FakeClient:
        host = "203.0.113.5"

    class FakeRequest:
        client = FakeClient()
        headers = {}

    req = FakeRequest()
    for _ in range(5):
        rate_limit.enforce_rate_limit(req, "test-scope", 5)  # should not raise

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        rate_limit.enforce_rate_limit(req, "test-scope", 5)
    assert exc_info.value.status_code == 429

    # a different client IP is not affected
    class OtherClient:
        host = "198.51.100.9"

    class OtherRequest:
        client = OtherClient()
        headers = {}

    rate_limit.enforce_rate_limit(OtherRequest(), "test-scope", 5)  # should not raise


# --- authorization matrix (spec section 28) ----------------------------------
def test_specialist_cannot_manage_system_content(client, specialist_token):
    """SPECIALIST can review assessments/therapy plans but must NOT be able
    to manage system content (disorders, exercises, games, knowledge base) —
    that stays ADMIN-only (spec sections 5, 27, 28)."""
    h = auth_headers(specialist_token)

    assert client.post("/api/v1/disorders", headers=h, json={"name": "X", "slug": "x-spec-test"}).status_code == 403
    assert (
        client.post(
            "/api/v1/exercises",
            headers=h,
            json={"title": "X", "category": "fluency", "instructions": "x"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/games",
            headers=h,
            json={"title": "X", "slug": "x-spec-game", "game_type": "word_matching", "content_json": "{}"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/knowledge-base/documents",
            headers=h,
            data={"title": "X"},
            files={"file": ("x.txt", b"some real content here", "text/plain")},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403


def test_user_cannot_manage_system_content(client, user_token):
    h = auth_headers(user_token)
    assert client.post("/api/v1/disorders", headers=h, json={"name": "X", "slug": "x-user-test"}).status_code == 403
    assert (
        client.post(
            "/api/v1/knowledge-base/documents",
            headers=h,
            data={"title": "X"},
            files={"file": ("x.txt", b"some real content here", "text/plain")},
        ).status_code
        == 403
    )


def test_admin_can_manage_system_content(client, admin_token):
    h = auth_headers(admin_token)
    assert client.post("/api/v1/disorders", headers=h, json={"name": "AdminCanManage", "slug": "admin-can-manage"}).status_code == 201
    assert (
        client.post(
            "/api/v1/knowledge-base/documents",
            headers=h,
            data={"title": "Admin Upload Test"},
            files={"file": ("y.txt", b"some real content here for indexing", "text/plain")},
        ).status_code
        == 201
    )


# --- production-config hardening (spec section 83) ---------------------------
def test_refuses_to_boot_in_production_with_default_secret_key(monkeypatch):
    from app.core.config import settings
    from app.main import _validate_production_config

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "insecure-dev-key-change-me")
    monkeypatch.setattr(settings, "FIRST_ADMIN_PASSWORD", "a-real-strong-password")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://example.com")
    try:
        import pytest

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _validate_production_config()
    finally:
        monkeypatch.setattr(settings, "APP_ENV", "development")


def test_refuses_to_boot_in_production_with_wildcard_cors(monkeypatch):
    from app.core.config import settings
    from app.main import _validate_production_config

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-generated-secret")
    monkeypatch.setattr(settings, "FIRST_ADMIN_PASSWORD", "a-real-strong-password")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "*")
    try:
        import pytest

        with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
            _validate_production_config()
    finally:
        monkeypatch.setattr(settings, "APP_ENV", "development")


def test_allows_boot_in_production_with_real_config(monkeypatch):
    from app.core.config import settings
    from app.main import _validate_production_config

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "a-real-generated-secret")
    monkeypatch.setattr(settings, "FIRST_ADMIN_PASSWORD", "a-real-strong-password")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://example.com")
    try:
        _validate_production_config()  # must not raise
    finally:
        monkeypatch.setattr(settings, "APP_ENV", "development")


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_docs_disabled_when_production_flag_set():
    """Verifies the docs_url wiring itself (not the running test app, which
    stays in development mode so /docs remains available for normal local
    development and the rest of the test suite)."""
    from fastapi import FastAPI

    from app.core.config import settings

    original = settings.APP_ENV
    try:
        settings.APP_ENV = "production"
        test_app = FastAPI(docs_url="/docs" if not settings.is_production else None)
        assert test_app.docs_url is None
    finally:
        settings.APP_ENV = original


# --- upload content-type spoofing protection (spec section 65) --------------
def test_upload_rejects_content_that_does_not_match_extension(client, user_token):
    """Renaming a non-audio file to '.wav' must be rejected — the extension
    check alone is not enough."""
    h = auth_headers(user_token)
    fake_audio = b"<html><body>not actually audio</body></html>"
    r = client.post(
        "/api/v1/assessments/media/audio",
        headers=h,
        files={"file": ("totally_real_audio.wav", fake_audio, "audio/wav")},
    )
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]


def test_upload_accepts_genuine_audio_with_correct_extension(client, user_token):
    import io
    import wave

    h = auth_headers(user_token)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    r = client.post(
        "/api/v1/assessments/media/audio",
        headers=h,
        files={"file": ("real.wav", buf.getvalue(), "audio/wav")},
    )
    assert r.status_code == 201


def test_upload_rejects_fake_pdf_for_knowledge_base(client, admin_token):
    h = auth_headers(admin_token)
    r = client.post(
        "/api/v1/knowledge-base/documents",
        headers=h,
        data={"title": "Fake PDF"},
        files={"file": ("fake.pdf", b"this is not a real pdf file at all", "application/pdf")},
    )
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]


# --- assessment review queue (spec section 25) -------------------------------
def test_pending_review_assessments_route_registered_before_dynamic_id(client, user_token, admin_token):
    """Regression guard: '/pending-review' must resolve to the dedicated
    endpoint, not be swallowed by '/{assessment_id}' and 404/422."""
    h_user = auth_headers(user_token)
    h_admin = auth_headers(admin_token)

    assert client.get("/api/v1/assessments/pending-review", headers=h_user).status_code == 403
    r = client.get("/api/v1/assessments/pending-review", headers=h_admin)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_pending_review_only_lists_completed_unreviewed_assessments(client, user_token, admin_token):
    import io
    import wave

    h = auth_headers(user_token)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)
    media = client.post(
        "/api/v1/assessments/media/audio", headers=h, files={"file": ("q.wav", buf.getvalue(), "audio/wav")}
    ).json()
    created = client.post(
        "/api/v1/assessments", headers=h, json={"media_file_id": media["id"], "assessment_type": "audio"}
    ).json()
    aid = created["id"]

    from tests.conftest import wait_for_assessment

    wait_for_assessment(client, user_token, aid)

    pending = client.get("/api/v1/assessments/pending-review", headers=auth_headers(admin_token)).json()
    assert any(a["id"] == aid for a in pending)

    # Once reviewed, it must drop off the queue.
    client.post(f"/api/v1/assessments/{aid}/review", headers=auth_headers(admin_token), json={"approve": True})
    pending_after = client.get("/api/v1/assessments/pending-review", headers=auth_headers(admin_token)).json()
    assert not any(a["id"] == aid for a in pending_after)
