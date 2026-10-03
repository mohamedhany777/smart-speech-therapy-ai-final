from tests.conftest import auth_headers


def test_admin_can_create_exercise_and_user_can_list(client, admin_token):
    resp = client.post(
        "/api/v1/exercises",
        json={
            "title": "Slow Speech Practice",
            "category": "fluency",
            "instructions": "Read slowly.",
            "duration_minutes": 10,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    exercise_id = resp.json()["id"]

    list_resp = client.get("/api/v1/exercises?category=fluency")
    assert list_resp.status_code == 200
    assert any(e["id"] == exercise_id for e in list_resp.json())


def test_regular_user_cannot_create_exercise(client, user_token):
    resp = client.post(
        "/api/v1/exercises",
        json={"title": "X", "category": "fluency", "instructions": "..."},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_user_can_complete_exercise_and_see_history(client, admin_token, user_token):
    create_resp = client.post(
        "/api/v1/exercises",
        json={"title": "Breathing", "category": "voice", "instructions": "Breathe deeply."},
        headers=auth_headers(admin_token),
    )
    exercise_id = create_resp.json()["id"]

    complete_resp = client.post(
        f"/api/v1/exercises/{exercise_id}/complete",
        json={"score": 85, "notes": "Went well"},
        headers=auth_headers(user_token),
    )
    assert complete_resp.status_code == 201
    assert complete_resp.json()["score"] == 85

    history_resp = client.get("/api/v1/exercises/me/history", headers=auth_headers(user_token))
    assert history_resp.status_code == 200
    assert any(c["exercise_id"] == exercise_id for c in history_resp.json())


def test_complete_nonexistent_exercise_returns_404(client, user_token):
    import uuid

    resp = client.post(
        f"/api/v1/exercises/{uuid.uuid4().hex}/complete",
        json={"score": 50},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 404
