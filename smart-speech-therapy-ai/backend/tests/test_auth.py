def test_register_creates_user_with_default_role(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "user1@example.com", "password": "StrongPass123", "full_name": "User One"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "user1@example.com"
    assert body["roles"] == ["USER"]


def test_register_duplicate_email_rejected(client):
    payload = {"email": "dup@example.com", "password": "StrongPass123", "full_name": "Dup"}
    client.post("/api/v1/auth/register", json=payload)
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_and_me_flow(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "StrongPass123", "full_name": "Login User"},
    )
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "StrongPass123"}
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    me_resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "login@example.com"


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpw@example.com", "password": "StrongPass123", "full_name": "X"},
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "WrongPassword"}
    )
    assert resp.status_code == 401


def test_refresh_token_rotates_and_old_one_is_invalid(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "StrongPass123", "full_name": "R"},
    )
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": "refresh@example.com", "password": "StrongPass123"}
    )
    old_refresh = login_resp.json()["refresh_token"]

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200

    reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_regular_user_cannot_access_admin_endpoint(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "notadmin@example.com", "password": "StrongPass123", "full_name": "N"},
    )
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": "notadmin@example.com", "password": "StrongPass123"}
    )
    token = login_resp.json()["access_token"]

    resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_health_and_ready_endpoints(client):
    assert client.get("/health").status_code == 200
    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["status"] == "ok"
