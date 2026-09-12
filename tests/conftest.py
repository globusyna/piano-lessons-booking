import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.store import store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    store.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/token", json={"username": "admin", "password": "piano"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}
