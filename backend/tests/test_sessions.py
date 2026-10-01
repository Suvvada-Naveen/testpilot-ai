import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(settings=Settings(_env_file=None)))


def valid_payload() -> dict[str, str]:
    return {
        "url": "https://example.com",
        "instruction": "Test the login functionality",
        "mode": "TEST",
    }


def test_create_valid_session(client: TestClient) -> None:
    response = client.post("/api/test-sessions", json=valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "TEST-001"
    assert body["url"] == "https://example.com"
    assert body["instruction"] == "Test the login functionality"
    assert body["mode"] == "TEST"
    assert body["status"] == "PENDING"
    assert body["created_at"] == body["updated_at"]


def test_reject_invalid_url(client: TestClient) -> None:
    response = client.post("/api/test-sessions", json={**valid_payload(), "url": "ftp://example.com"})

    assert response.status_code == 422
    assert "http:// or https://" in response.text


@pytest.mark.parametrize("instruction", ["", "   ", "\n\t"])
def test_reject_empty_instruction(client: TestClient, instruction: str) -> None:
    response = client.post("/api/test-sessions", json={**valid_payload(), "instruction": instruction})

    assert response.status_code == 422
    assert "Instruction cannot be empty or whitespace" in response.text


def test_reject_invalid_mode(client: TestClient) -> None:
    response = client.post("/api/test-sessions", json={**valid_payload(), "mode": "BROWSE"})

    assert response.status_code == 422


def test_get_session(client: TestClient) -> None:
    created = client.post("/api/test-sessions", json=valid_payload()).json()

    response = client.get(f"/api/test-sessions/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_all_sessions(client: TestClient) -> None:
    client.post("/api/test-sessions", json=valid_payload())
    client.post("/api/test-sessions", json={**valid_payload(), "mode": "EXPLORE"})

    response = client.get("/api/test-sessions")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["mode"] == "EXPLORE"


def test_get_nonexistent_session(client: TestClient) -> None:
    response = client.get("/api/test-sessions/TEST-999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Testing session not found"}


def test_delete_session(client: TestClient) -> None:
    created = client.post("/api/test-sessions", json=valid_payload()).json()

    response = client.delete(f"/api/test-sessions/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/test-sessions/{created['id']}").status_code == 404


def test_delete_nonexistent_session(client: TestClient) -> None:
    response = client.delete("/api/test-sessions/TEST-999")

    assert response.status_code == 404