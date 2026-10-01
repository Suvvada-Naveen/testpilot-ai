from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.test_session import TestMode, TestStatus


class CreateTestSessionRequest(BaseModel):
    url: str
    instruction: str
    mode: TestMode

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
        except ValueError as error:
            raise ValueError("URL must be a valid HTTP or HTTPS URL") from error

        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname:
            raise ValueError("URL must be a valid HTTP or HTTPS URL")
        return value

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Instruction cannot be empty or whitespace")
        return value


class TestSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    instruction: str
    mode: TestMode
    status: TestStatus
    created_at: datetime
    updated_at: datetime