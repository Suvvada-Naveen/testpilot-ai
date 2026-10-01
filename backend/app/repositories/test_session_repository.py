from datetime import UTC, datetime
from dataclasses import replace
from threading import RLock

from app.models.test_session import TestMode, TestSession, TestStatus


class TestSessionRepository:
    """Thread-safe in-memory store; replace this adapter to persist sessions later."""

    def __init__(self) -> None:
        self._sessions: dict[str, TestSession] = {}
        self._inspections: dict[str, dict[str, object]] = {}
        self._next_id = 1
        self._lock = RLock()

    def create(self, url: str, instruction: str, mode: TestMode) -> TestSession:
        with self._lock:
            now = datetime.now(UTC)
            session = TestSession(
                id=f"TEST-{self._next_id:03d}",
                url=url,
                instruction=instruction,
                mode=mode,
                status=TestStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
            self._next_id += 1
            self._sessions[session.id] = session
            return session

    def get_by_id(self, session_id: str) -> TestSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def get_all(self) -> list[TestSession]:
        with self._lock:
            return list(reversed(self._sessions.values()))

    def delete(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
            self._inspections.pop(session_id, None)
            return removed

    def update_status(self, session_id: str, status: TestStatus) -> TestSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            updated = replace(session, status=status, updated_at=datetime.now(UTC))
            self._sessions[session_id] = updated
            return updated

    def save_inspection(self, session_id: str, result: dict[str, object]) -> None:
        with self._lock:
            self._inspections[session_id] = result

    def get_inspection(self, session_id: str) -> dict[str, object] | None:
        with self._lock:
            return self._inspections.get(session_id)