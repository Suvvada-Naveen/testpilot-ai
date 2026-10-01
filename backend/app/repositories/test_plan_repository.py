from threading import RLock

from app.schemas.test_plan import TestPlan


class TestPlanRepository:
    """Thread-safe in-memory plan storage; replaceable with a persistent adapter."""

    def __init__(self) -> None:
        self._plans: dict[str, TestPlan] = {}
        self._lock = RLock()

    def create(self, session_id: str, test_plan: TestPlan) -> TestPlan:
        with self._lock:
            stored_plan = test_plan.model_copy(deep=True)
            self._plans[session_id] = stored_plan
            return stored_plan.model_copy(deep=True)

    def get_by_session_id(self, session_id: str) -> TestPlan | None:
        with self._lock:
            test_plan = self._plans.get(session_id)
            return test_plan.model_copy(deep=True) if test_plan is not None else None

    def delete_by_session_id(self, session_id: str) -> bool:
        with self._lock:
            return self._plans.pop(session_id, None) is not None