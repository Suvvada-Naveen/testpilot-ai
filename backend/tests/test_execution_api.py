from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.test_execution import ActionExecution, ActionExecutionStatus, TestExecutionResult as ExecutionResult
from app.schemas.test_execution import TestExecutionStatus as ExecutionStatus
from app.schemas.test_plan import TestCase as PlanCase
from app.schemas.test_plan import TestCaseType as PlanCaseType
from app.schemas.test_plan import TestPlan as Plan
from app.schemas.test_plan import TestPriority as PlanPriority


def plan() -> Plan:
    return Plan(
        summary="Login validation plan",
        warnings=[],
        test_cases=[
            PlanCase(
                id="TC001", title="Missing username", type=PlanCaseType.VALIDATION,
                priority=PlanPriority.HIGH, description="Require a username.", preconditions=[],
                steps=["Click Login"], expected_result="Username is required.",
                target_elements=["Login button"],
            ),
            PlanCase(
                id="TC002", title="Missing password", type=PlanCaseType.VALIDATION,
                priority=PlanPriority.MEDIUM, description="Require a password.", preconditions=[],
                steps=["Click Login"], expected_result="Password is required.",
                target_elements=["Login button"],
            ),
        ],
    )


class FakeExecutionService:
    def __init__(self, repository: ExecutionRepository) -> None:
        self.repository = repository
        self.calls: list[tuple[str, str, str, bool]] = []

    async def execute_test_case(self, session_id: str, test_case: PlanCase, url: str, confirm_destructive: bool = False) -> ExecutionResult:
        self.calls.append((session_id, test_case.id, url, confirm_destructive))
        now = datetime.now(UTC)
        result = ExecutionResult(
            id=f"EXEC-{test_case.id}", session_id=session_id, test_case_id=test_case.id,
            status=ExecutionStatus.PASSED, started_at=now, completed_at=now, duration=1.25,
            actions=[ActionExecution(
                step=1, action="click", target="Login", status=ActionExecutionStatus.SUCCESS, duration_ms=90,
            )],
            expected_result=test_case.expected_result, actual_result=test_case.expected_result,
        )
        return self.repository.create_execution(result)


def make_client(max_tests: int = 10) -> tuple[TestClient, FakeExecutionService, str]:
    settings = Settings(_env_file=None, max_test_cases_per_execution=max_tests)
    repository = ExecutionRepository()
    execution_service = FakeExecutionService(repository)
    app = create_app(settings=settings, execution_repository=repository, execution_service=execution_service)
    client = TestClient(app)
    session = client.post("/api/test-sessions", json={
        "url": "https://example.com/login", "instruction": "Test login", "mode": "TEST",
    }).json()
    return client, execution_service, session["id"]


def add_plan(client: TestClient, session_id: str) -> None:
    app = client.app
    app.state.test_plan_repository.create(session_id, plan())


def test_execution_requires_existing_session_and_plan() -> None:
    client, execution_service, session_id = make_client()

    no_plan = client.post(f"/api/test-sessions/{session_id}/test-cases/TC001/execute")
    no_session = client.post("/api/test-sessions/TEST-404/execute", json={"test_case_ids": ["TC001"]})

    assert no_plan.status_code == 404
    assert no_plan.json() == {"detail": "No test plan has been generated"}
    assert no_session.status_code == 404
    assert no_session.json() == {"detail": "Testing session not found"}
    assert execution_service.calls == []


def test_single_execution_returns_result_and_session_history() -> None:
    client, execution_service, session_id = make_client()
    add_plan(client, session_id)

    response = client.post(
        f"/api/test-sessions/{session_id}/test-cases/TC001/execute",
        json={"confirm_destructive": True},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["test_case_id"] == "TC001"
    assert result["status"] == "PASSED"
    assert result["duration"] == 1.25
    assert result["actions"][0]["target"] == "Login"
    assert execution_service.calls == [(session_id, "TC001", "https://example.com/login", True)]
    assert client.get(f"/api/test-sessions/{session_id}/executions").json() == [result]
    assert client.get(f"/api/test-sessions/{session_id}/executions/{result['id']}").json() == result


def test_selected_execution_is_capped_and_unknown_cases_rejected() -> None:
    client, execution_service, session_id = make_client(max_tests=1)
    add_plan(client, session_id)

    too_many = client.post(f"/api/test-sessions/{session_id}/execute")
    unknown = client.post(f"/api/test-sessions/{session_id}/execute", json={"test_case_ids": ["TC999"]})
    selected = client.post(
        f"/api/test-sessions/{session_id}/execute",
        json={"test_case_ids": ["TC002"], "confirm_destructive": False},
    )

    assert too_many.status_code == 422
    assert "maximum of 1" in too_many.json()["detail"]
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "One or more selected test cases were not found"}
    assert selected.status_code == 200
    assert selected.json()["total"] == 1
    assert selected.json()["executions"][0]["test_case_id"] == "TC002"
    assert execution_service.calls[-1][1] == "TC002"


def test_get_execution_is_scoped_to_session() -> None:
    client, _, first_session = make_client()
    add_plan(client, first_session)
    execution = client.post(f"/api/test-sessions/{first_session}/test-cases/TC001/execute").json()
    second = client.post("/api/test-sessions", json={
        "url": "https://example.com", "instruction": "Explore", "mode": "EXPLORE",
    }).json()["id"]

    response = client.get(f"/api/test-sessions/{second}/executions/{execution['id']}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Test execution not found"}
