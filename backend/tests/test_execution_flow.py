import http.server
import threading
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.execution.execution_service import ExecutionService
from app.main import create_app
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.browser_action import BrowserAction, BrowserToolName, EvaluationStatus, ProgressEvaluation
from app.schemas.test_plan import TestCase as PlanCase
from app.schemas.test_plan import TestCaseType as PlanCaseType
from app.schemas.test_plan import TestPlan as Plan
from app.schemas.test_plan import TestPriority as PlanPriority

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


class QuietFixtureHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class LoginPlanAgent:
    def __init__(self, test_plan: Plan) -> None:
        self.test_plan = test_plan

    async def generate_test_plan(self, session_id: str, instruction: str, inspection: object) -> Plan:
        return self.test_plan


class LoginActionPlanner:
    def __init__(self) -> None:
        self._actions = [
            BrowserAction(action=BrowserToolName.FILL, target="Password field", value="[MOCK_PASSWORD]", reason="Enter the configured mock password to trigger username validation."),
            BrowserAction(action=BrowserToolName.CLICK, target="Login", reason="Submit the login form and observe required username validation."),
        ]
        self._index = 0

    async def next_action(self, test_case: PlanCase, page_state: dict[str, Any], previous_actions: list[dict[str, Any]], action_results: list[dict[str, Any]]) -> BrowserAction:
        action = self._actions[self._index]
        self._index += 1
        return action


class LoginResultEvaluator:
    async def evaluate(self, test_case: PlanCase, page_state: dict[str, Any], action_history: list[dict[str, Any]], console_errors: list[dict[str, str]], network_errors: list[dict[str, str]]) -> ProgressEvaluation:
        if test_case.expected_result in str(page_state.get("visible_text", "")):
            return ProgressEvaluation(
                finished=True,
                status=EvaluationStatus.PASS,
                reason="The username-required validation appeared after form submission.",
                evidence=[test_case.expected_result],
            )
        return ProgressEvaluation(finished=False, status=EvaluationStatus.CONTINUE, reason="Continue with the next approved action.")


def test_inspect_generate_execute_and_retrieve_local_login_validation() -> None:
    handler = lambda *args, **kwargs: QuietFixtureHandler(*args, directory=str(FIXTURE_DIRECTORY), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/login_page.html"
        test_plan = Plan(
            summary="Login required-field plan",
            warnings=[],
            test_cases=[PlanCase(
                id="TC001",
                title="Required username validation",
                type=PlanCaseType.VALIDATION,
                priority=PlanPriority.HIGH,
                description="Verify the login form explains that a username is required.",
                preconditions=[],
                steps=["Enter the mock password", "Click Login"],
                expected_result="Username is required.",
                target_elements=["Password field", "Login button"],
                requires_credentials=True,
            )],
        )
        settings = Settings(
            _env_file=None,
            allow_local_urls=True,
            browser_timeout=5000,
            navigation_timeout=5000,
            action_timeout=2000,
            max_actions_per_test=10,
            test_credential_password=SecretStr("fixture-password"),
        )
        execution_repository = ExecutionRepository()
        execution_service = ExecutionService(
            execution_repository,
            LoginActionPlanner(),
            LoginResultEvaluator(),
            settings,
        )
        app = create_app(
            settings=settings,
            testing_agent=LoginPlanAgent(test_plan),
            execution_repository=execution_repository,
            execution_service=execution_service,
        )
        client = TestClient(app)

        session = client.post("/api/test-sessions", json={
            "url": url,
            "instruction": "Verify required username validation.",
            "mode": "TEST",
        }).json()
        session_id = session["id"]

        inspected = client.post(f"/api/test-sessions/{session_id}/inspect")
        generated = client.post(f"/api/test-sessions/{session_id}/generate-tests")
        executed = client.post(f"/api/test-sessions/{session_id}/test-cases/TC001/execute")

        assert inspected.status_code == 200
        assert inspected.json()["page"]["title"] == "TestPilot Login Fixture"
        assert generated.status_code == 200
        assert generated.json()["test_cases"][0]["id"] == "TC001"
        assert executed.status_code == 200
        result = executed.json()
        assert result["status"] == "PASSED"
        assert result["test_case_id"] == "TC001"
        assert "Username is required." in result["actual_result"]
        assert result["screenshot_id"]
        assert all("fixture-password" not in str(action) for action in result["actions"])

        history = client.get(f"/api/test-sessions/{session_id}/executions")
        details = client.get(f"/api/test-sessions/{session_id}/executions/{result['id']}")
        screenshot = client.get(f"/api/test-sessions/{session_id}/executions/{result['id']}/screenshot")
        assert history.status_code == 200 and history.json()[0]["status"] == "PASSED"
        assert details.json() == result
        assert screenshot.status_code == 200
        assert screenshot.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
