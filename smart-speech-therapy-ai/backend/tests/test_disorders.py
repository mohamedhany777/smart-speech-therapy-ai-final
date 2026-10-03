from tests.conftest import auth_headers


def test_admin_can_create_category_and_disorder(client, admin_token):
    cat_resp = client.post(
        "/api/v1/disorders/categories",
        json={"name": "Fluency Disorders", "description": "Test category"},
        headers=auth_headers(admin_token),
    )
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    disorder_resp = client.post(
        "/api/v1/disorders",
        json={
            "name": "Stuttering",
            "slug": "stuttering-test",
            "category_id": category_id,
            "overview": "A fluency disorder.",
        },
        headers=auth_headers(admin_token),
    )
    assert disorder_resp.status_code == 201
    assert disorder_resp.json()["slug"] == "stuttering-test"


def test_regular_user_cannot_create_disorder(client, user_token):
    resp = client.post(
        "/api/v1/disorders",
        json={"name": "X", "slug": "x-disorder-test"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_anyone_can_list_and_get_disorder(client, admin_token):
    client.post(
        "/api/v1/disorders",
        json={"name": "Cluttering", "slug": "cluttering-test", "overview": "Overview text"},
        headers=auth_headers(admin_token),
    )

    list_resp = client.get("/api/v1/disorders")
    assert list_resp.status_code == 200
    slugs = [d["slug"] for d in list_resp.json()]
    assert "cluttering-test" in slugs

    get_resp = client.get("/api/v1/disorders/cluttering-test")
    assert get_resp.status_code == 200
    assert get_resp.json()["overview"] == "Overview text"


def test_get_unknown_disorder_returns_404(client):
    resp = client.get("/api/v1/disorders/does-not-exist")
    assert resp.status_code == 404


def test_duplicate_slug_rejected(client, admin_token):
    payload = {"name": "Dup Disorder", "slug": "dup-disorder-test"}
    client.post("/api/v1/disorders", json=payload, headers=auth_headers(admin_token))
    resp = client.post("/api/v1/disorders", json=payload, headers=auth_headers(admin_token))
    assert resp.status_code == 409


def test_syndrome_crud(client, admin_token, user_token):
    create_resp = client.post(
        "/api/v1/disorders/syndromes",
        json={"name": "Down syndrome", "slug": "down-syndrome-test", "description": "Genetic condition."},
        headers=auth_headers(admin_token),
    )
    assert create_resp.status_code == 201

    list_resp = client.get("/api/v1/disorders/syndromes")
    assert list_resp.status_code == 200
    assert any(s["slug"] == "down-syndrome-test" for s in list_resp.json())

    forbidden_resp = client.post(
        "/api/v1/disorders/syndromes",
        json={"name": "X syndrome", "slug": "x-syndrome-test"},
        headers=auth_headers(user_token),
    )
    assert forbidden_resp.status_code == 403
