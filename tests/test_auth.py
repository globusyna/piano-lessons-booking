from fastapi.testclient import TestClient

from backend.store import store


def test_seeded_password_is_hashed() -> None:
    assert store.admin_password_hash != "piano"
    assert store.admin_password_hash.startswith("$argon2")


def test_login_returns_bearer_token(client: TestClient) -> None:
    response = client.post("/auth/token", json={"username": "admin", "password": "piano"})

    assert response.status_code == 200
    assert response.json()["tokenType"] == "bearer"
    assert response.json()["accessToken"]


def test_bad_login_and_protected_route_are_rejected(client: TestClient) -> None:
    bad_login = client.post("/auth/token", json={"username": "admin", "password": "wrong"})
    protected = client.get("/admin/students")

    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "UNAUTHENTICATED"
    assert protected.status_code == 401
    assert protected.json()["error"]["code"] == "UNAUTHENTICATED"
