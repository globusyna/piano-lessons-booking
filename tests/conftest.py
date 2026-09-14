import os

import pytest
from fastapi.testclient import TestClient

# Never let the destructive reset fixture target a developer or production database.
os.environ["PIANO_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
# The suite signs real admin tokens, so it needs a real signing secret. Dev mode generates one
# per run; an explicitly set PIANO_JWT_SECRET still wins over it.
os.environ["PIANO_DEV_MODE"] = "1"

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
