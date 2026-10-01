import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Page


SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "screenshots"


class ScreenshotManager:
    def __init__(self, directory: Path = SCREENSHOTS_DIR) -> None:
        self.directory = directory

    async def capture(self, page: Page, session_id: str) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        safe_session_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        screenshot_id = f"{safe_session_id}_{timestamp}_{uuid4().hex[:8]}.png"
        await page.screenshot(path=str(self.directory / screenshot_id), full_page=True)
        return screenshot_id