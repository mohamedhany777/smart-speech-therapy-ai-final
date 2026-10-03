import io

from tests.conftest import auth_headers


def test_admin_can_update_disorder(client, admin_token):
    create_resp = client.post(
        "/api/v1/disorders",
        json={"name": "Cluttering", "slug": "cluttering-update-test", "overview": "Original overview"},
        headers=auth_headers(admin_token),
    )
    disorder_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"/api/v1/disorders/{disorder_id}",
        json={"overview": "Updated overview text", "speech_features": "New speech features"},
        headers=auth_headers(admin_token),
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["overview"] == "Updated overview text"
    assert body["speech_features"] == "New speech features"
    assert body["name"] == "Cluttering"  # untouched fields stay the same


def test_update_disorder_rejects_duplicate_slug(client, admin_token):
    client.post(
        "/api/v1/disorders",
        json={"name": "A", "slug": "slug-a-test"},
        headers=auth_headers(admin_token),
    )
    create_b = client.post(
        "/api/v1/disorders",
        json={"name": "B", "slug": "slug-b-test"},
        headers=auth_headers(admin_token),
    )
    b_id = create_b.json()["id"]

    resp = client.patch(
        f"/api/v1/disorders/{b_id}",
        json={"slug": "slug-a-test"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 409


def test_regular_user_cannot_update_disorder(client, admin_token, user_token):
    create_resp = client.post(
        "/api/v1/disorders",
        json={"name": "X", "slug": "x-update-test"},
        headers=auth_headers(admin_token),
    )
    disorder_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/disorders/{disorder_id}",
        json={"overview": "hacked"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_update_nonexistent_disorder_returns_404(client, admin_token):
    import uuid

    resp = client.patch(
        f"/api/v1/disorders/{uuid.uuid4().hex}",
        json={"overview": "x"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


def test_admin_can_update_syndrome(client, admin_token):
    create_resp = client.post(
        "/api/v1/disorders/syndromes",
        json={"name": "Test Syndrome", "slug": "test-syndrome-update"},
        headers=auth_headers(admin_token),
    )
    syndrome_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"/api/v1/disorders/syndromes/{syndrome_id}",
        json={"description": "Updated description"},
        headers=auth_headers(admin_token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Updated description"


def test_admin_can_update_exercise(client, admin_token):
    create_resp = client.post(
        "/api/v1/exercises",
        json={"title": "Original Title", "category": "voice", "instructions": "Do the thing."},
        headers=auth_headers(admin_token),
    )
    exercise_id = create_resp.json()["id"]

    update_resp = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"title": "Updated Title", "difficulty": "advanced"},
        headers=auth_headers(admin_token),
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["title"] == "Updated Title"
    assert body["difficulty"] == "advanced"
    assert body["category"] == "voice"  # untouched


def test_regular_user_cannot_update_exercise(client, admin_token, user_token):
    create_resp = client.post(
        "/api/v1/exercises",
        json={"title": "T", "category": "voice", "instructions": "..."},
        headers=auth_headers(admin_token),
    )
    exercise_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"title": "hacked"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_disorder_extraction_unavailable_without_openai_key(client, admin_token):
    resp = client.post(
        "/api/v1/disorders/extract-from-document",
        files={"file": ("info.txt", io.BytesIO(b"Some text about a speech disorder."), "text/plain")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "OPENAI_API_KEY" in body["note"]
    # A graceful "unavailable" response must not fabricate content.
    assert body["overview"] is None
    assert body["suggested_name"] is None


def test_disorder_extraction_requires_admin(client, user_token):
    resp = client.post(
        "/api/v1/disorders/extract-from-document",
        files={"file": ("info.txt", io.BytesIO(b"Some text."), "text/plain")},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_disorder_extraction_rejects_unsupported_file_type(client, admin_token):
    resp = client.post(
        "/api/v1/disorders/extract-from-document",
        files={"file": ("bad.exe", io.BytesIO(b"binary"), "application/octet-stream")},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


def test_include_inactive_disorders_and_exercises(client, admin_token):
    create_resp = client.post(
        "/api/v1/disorders",
        json={"name": "Deactivatable", "slug": "deactivatable-test"},
        headers=auth_headers(admin_token),
    )
    disorder_id = create_resp.json()["id"]
    client.patch(f"/api/v1/disorders/{disorder_id}", json={"is_active": False}, headers=auth_headers(admin_token))

    default_list = client.get("/api/v1/disorders").json()
    assert not any(d["id"] == disorder_id for d in default_list)

    full_list = client.get("/api/v1/disorders?include_inactive=true", headers=auth_headers(admin_token)).json()
    assert any(d["id"] == disorder_id for d in full_list)
