from urllib.parse import urlsplit

from app.models.test_session import TestMode, TestSession, TestStatus
from app.repositories.test_session_repository import TestSessionRepository
from app.schemas.test_session import CreateTestSessionRequest


class SessionValidationError(ValueError):
    pass


class TestSessionService:
    def __init__(self, repository: TestSessionRepository) -> None:
        self._repository = repository

    def create(self, request: CreateTestSessionRequest) -> TestSession:
        url = request.url.strip()
        instruction = request.instruction.strip()
        parsed = urlsplit(url)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SessionValidationError("URL must use http:// or https://")
        if not instruction:
            raise SessionValidationError("Instruction cannot be empty or whitespace")
        if not isinstance(request.mode, TestMode):
            raise SessionValidationError("Mode must be EXPLORE, TEST, or FULL_TEST")

        return self._repository.create(url, instruction, request.mode)

    def get(self, session_id: str) -> TestSession | None:
        return self._repository.get_by_id(session_id)

    def list(self) -> list[TestSession]:
        return self._repository.get_all()

    def delete(self, session_id: str) -> bool:
        return self._repository.delete(session_id)

    def update_status(self, session_id: str, status: TestStatus) -> TestSession | None:
        return self._repository.update_status(session_id, status)

    def save_inspection(self, session_id: str, result: dict[str, object]) -> None:
        self._repository.save_inspection(session_id, result)

    def get_inspection(self, session_id: str) -> dict[str, object] | None:
        return self._repository.get_inspection(session_id)