from threading import RLock

from app.schemas.test_execution import TestExecutionResult


class ExecutionRepository:
    """Thread-safe in-memory execution storage; replaceable with PostgreSQL later."""

    def __init__(self) -> None:
        self._executions: dict[str, TestExecutionResult] = {}
        self._session_ids: dict[str, list[str]] = {}
        self._lock = RLock()

    def create_execution(self, execution: TestExecutionResult) -> TestExecutionResult:
        with self._lock:
            stored = execution.model_copy(deep=True)
            self._executions[stored.id] = stored
            self._session_ids.setdefault(stored.session_id, []).append(stored.id)
            return stored.model_copy(deep=True)

    def update_execution(self, execution: TestExecutionResult) -> TestExecutionResult | None:
        with self._lock:
            if execution.id not in self._executions:
                return None
            self._executions[execution.id] = execution.model_copy(deep=True)
            return execution.model_copy(deep=True)

    def get_execution(self, session_id: str, execution_id: str) -> TestExecutionResult | None:
        with self._lock:
            execution = self._executions.get(execution_id)
            if execution is None or execution.session_id != session_id:
                return None
            return execution.model_copy(deep=True)

    def get_by_id(self, execution_id: str) -> TestExecutionResult | None:
        with self._lock:
            execution = self._executions.get(execution_id)
            return execution.model_copy(deep=True) if execution is not None else None

    def get_session_executions(self, session_id: str) -> list[TestExecutionResult]:
        with self._lock:
            ids = self._session_ids.get(session_id, [])
            return [self._executions[item].model_copy(deep=True) for item in ids if item in self._executions]

    def list_executions(self) -> list[TestExecutionResult]:
        with self._lock:
            return [execution.model_copy(deep=True) for execution in self._executions.values()]

    def delete_session_executions(self, session_id: str) -> None:
        with self._lock:
            for execution_id in self._session_ids.pop(session_id, []):
                self._executions.pop(execution_id, None)
