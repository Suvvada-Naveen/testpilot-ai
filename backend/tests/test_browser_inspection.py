import asyncio
import http.server
import socket
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.browser.browser_manager import BrowserManager
from app.core.config import Settings
from app.main import create_app
from app.services.browser_test_service import UrlValidationError, validate_url

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class QuietFixtureHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def fixture_url() -> str:
    handler = lambda *args, **kwargs: QuietFixtureHandler(*args, directory=str(FIXTURE_DIRECTORY), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/test_page.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def client() -> TestClient:
    settings = Settings(_env_file=None, allow_local_urls=True, browser_timeout=5000)
    return TestClient(create_app(settings=settings))


def create_session(client: TestClient, url: str) -> str:
    response = client.post("/api/test-sessions", json={
        "url": url,
        "instruction": "Inspect the page",
        "mode": "EXPLORE",
    })
    assert response.status_code == 201
    return response.json()["id"]


def test_valid_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    asyncio.run(validate_url("https://example.com/login"))


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,test", "ftp://example.com"])
def test_rejects_unsupported_url_protocols(url: str) -> None:
    with pytest.raises(UrlValidationError):
        asyncio.run(validate_url(url))


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1", "http://10.0.0.1", "http://[::1]"])
def test_rejects_local_and_private_addresses(url: str) -> None:
    with pytest.raises(UrlValidationError, match="Local and private"):
        asyncio.run(validate_url(url))


def test_browser_manager_closes_context_browser_and_playwright() -> None:
    async def check_cleanup() -> None:
        manager = BrowserManager()
        await manager.start()
        browser = manager.browser
        await manager.create_context()
        page = await manager.create_page()
        await manager.close_page(page)
        await manager.close()
        assert manager.context is None
        assert manager.browser is None
        assert manager._playwright is None
        assert browser is not None and not browser.is_connected()

    asyncio.run(check_cleanup())


def test_successful_inspection_extracts_page_and_serves_screenshot(
    client: TestClient,
    fixture_url: str,
) -> None:
    session_id = create_session(client, fixture_url)

    response = client.post(f"/api/test-sessions/{session_id}/inspect")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "COMPLETED"
    assert result["page"] == {
        "requested_url": fixture_url,
        "final_url": fixture_url,
        "status_code": 200,
        "title": "TestPilot Fixture",
    }
    assert result["visible_text"].startswith("Fixture heading")
    assert "Hidden text must not be returned." not in result["visible_text"]
    assert result["elements"]["headings"] == ["Fixture heading"]
    assert result["elements"]["buttons"][0] == {
        "text": "Continue", "aria_label": "Submit fixture", "disabled": False,
    }
    assert {item["type"] for item in result["elements"]["inputs"]} == {"text", "password"}
    assert result["elements"]["inputs"][1]["placeholder"] == "Secret value"
    assert result["elements"]["checkboxes"] == [{
        "name": "remember", "id": "", "checked": False, "required": True,
    }]
    assert result["elements"]["radio_buttons"][0]["checked"] is True
    assert result["elements"]["selects"][0]["options"][0]["text"] == "QA"
    assert result["elements"]["links"] == [{"text": "Fixture help", "href": f"{fixture_url.rsplit('/', 1)[0]}/help"}]
    assert any(entry["text"].strip() == "fixture console error" for entry in result["console_errors"])
    assert any("127.0.0.1:54321" in issue["url"] for issue in result["network_errors"])

    screenshot = client.get(f"/api/test-sessions/{session_id}/inspection/screenshot")
    assert screenshot.status_code == 200
    assert screenshot.headers["content-type"] == "image/png"
    assert screenshot.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert client.get(f"/api/test-sessions/{session_id}").json()["status"] == "COMPLETED"


def test_failed_navigation_updates_status_and_returns_safe_error(client: TestClient) -> None:
    session_id = create_session(client, "http://127.0.0.1:54322/unavailable")

    response = client.post(f"/api/test-sessions/{session_id}/inspect")

    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"] == "Unable to connect to or load this website."
    assert "Traceback" not in response.text
    assert client.get(f"/api/test-sessions/{session_id}").json()["status"] == "FAILED"


def test_inspection_lookup_without_result_returns_404(client: TestClient) -> None:
    session_id = create_session(client, "https://example.com")

    response = client.get(f"/api/test-sessions/{session_id}/inspection")

    assert response.status_code == 404
    assert response.json() == {"detail": "No inspection found for this testing session"}


def test_localhost_inspection_is_blocked_by_default() -> None:
    client = TestClient(create_app(settings=Settings(_env_file=None, browser_timeout=5000)))
    session_id = create_session(client, "http://localhost:8000/")

    response = client.post(f"/api/test-sessions/{session_id}/inspect")

    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"] == "Local and private network addresses are not allowed."
    assert client.get(f"/api/test-sessions/{session_id}").json()["status"] == "FAILED"


def test_inspection_for_nonexistent_session_returns_404(client: TestClient) -> None:
    response = client.post("/api/test-sessions/TEST-999/inspect")

    assert response.status_code == 404
    assert response.json() == {"detail": "Testing session not found"}