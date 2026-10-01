from pydantic import BaseModel

from app.models.test_session import TestStatus


class PageInfo(BaseModel):
    requested_url: str
    final_url: str
    status_code: int | None
    title: str


class BrowserInspectionResponse(BaseModel):
    session_id: str
    status: TestStatus
    page: PageInfo
    elements: dict[str, object]
    visible_text: str
    screenshot_id: str
    console_errors: list[dict[str, str]]
    console_messages: list[dict[str, str]]
    network_errors: list[dict[str, str]]
    error: str | None = None