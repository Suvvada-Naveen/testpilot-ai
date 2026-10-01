import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.ai_client import AIClient
from app.analysis.bug_generator import BugGenerator
from app.analysis.failure_analyzer import FailureAnalyzer
from app.bug_reports.bug_report_repository import BugReportRepository
from app.bug_reports.bug_report_service import BugReportService
from app.core.config import Settings
from app.evidence.evidence_collector import EvidenceCollector
from app.evidence.evidence_repository import EvidenceRepository
from app.main import create_app
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.test_plan_repository import TestPlanRepository
from app.schemas.bug_report import BugPriority, BugReportDraft, BugReportStatus, BugSeverity
from app.schemas.evidence import Evidence, EvidenceType, FailureEvidenceBundle
from app.schemas.failure_analysis import AnalysisConfidence, FailureAnalysis, FailureClassification
from app.schemas.test_execution import ActionExecution, ActionExecutionStatus, TestExecutionResult, TestExecutionStatus
from app.schemas.test_plan import TestCase, TestCaseType, TestPlan, TestPriority


def case() -> TestCase:
    return TestCase(
        id="TC004", title="Required username validation", type=TestCaseType.VALIDATION,
        priority=TestPriority.HIGH, description="Show a username-required message.", preconditions=[],
        steps=["Leave the username empty", "Enter the mock password", "Click Login"],
        expected_result="Username is required.", target_elements=["Username field", "Login button"],
        requires_credentials=True,
    )


def execution(status: TestExecutionStatus = TestExecutionStatus.FAILED) -> TestExecutionResult:
    now = datetime.now(UTC)
    return TestExecutionResult(
        id="EXEC-001", session_id="TEST-001", test_case_id="TC004", status=status,
        started_at=now, completed_at=now, duration=2.4,
        actions=[
            ActionExecution(step=1, action="navigate", target="https://example.com/login", status=ActionExecutionStatus.SUCCESS, duration_ms=200),
            ActionExecution(step=2, action="fill", target="Password field", status=ActionExecutionStatus.SUCCESS, duration_ms=80),
            ActionExecution(step=3, action="click", target="Login", status=ActionExecutionStatus.SUCCESS, duration_ms=90),
        ],
        expected_result="Username is required.", actual_result="No validation message was displayed.",
        failure_reason="The expected validation message was not displayed.", screenshot_id="EXEC-001_20261001.png",
        actual_page_state={
            "url": "https://example.com/login?access_token=private-token",
            "title": "Login",
            "visible_text": "Login. Password=fixture-password. Card 4111 1111 1111 1111. No validation message was displayed.",
            "elements": {"headings": ["Login"], "buttons": [{"text": "Login"}], "inputs": [{"name": "password", "type": "password"}]},
        },
        console_errors=[{"type": "error", "text": "Authorization: Bearer hidden-auth-token"}],
        network_errors=[{"url": "https://example.com/api/login?token=private-token", "method": "POST", "failure": "HTTP 500"}],
    )


def defect_analysis(evidence_ids: list[str], *, confidence: AnalysisConfidence = AnalysisConfidence.HIGH) -> FailureAnalysis:
    return FailureAnalysis(
        execution_id="EXEC-001", classification=FailureClassification.APPLICATION_DEFECT,
        confidence=confidence,
        summary="The username validation message was absent after form submission.",
        expected_behavior="Username is required.",
        actual_behavior="No validation message was displayed.",
        evidence=evidence_ids,
        possible_causes=["Client-side validation may not be triggering."],
        recommended_next_step="Review the form validation behavior.", needs_review=False,
    )


class FakeStructuredAI:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[tuple[str, str, type[Any]]] = []

    async def generate_structured_response(self, system_prompt: str, user_message: str, response_model: type[Any]) -> Any:
        self.requests.append((system_prompt, user_message, response_model))
        if self.error:
            raise self.error
        return self.response


def test_failure_evidence_is_complete_bounded_and_masks_sensitive_data() -> None:
    settings = Settings(
        _env_file=None,
        test_credential_username="fixture-user@example.test",
        test_credential_password=SecretStr("fixture-password"),
        max_failure_evidence_items=20,
    )
    repository = EvidenceRepository()
    collector = EvidenceCollector(repository, settings)

    bundle = collector.collect_failure(case(), execution(), "https://example.com/login?token=private-token")

    evidence_types = {item.type for item in bundle.evidence}
    assert evidence_types == {
        EvidenceType.SCREENSHOT, EvidenceType.PAGE_STATE, EvidenceType.ACTION_LOG,
        EvidenceType.PAGE_TEXT, EvidenceType.CONSOLE_ERROR, EvidenceType.NETWORK_ERROR,
        EvidenceType.EXECUTION_LOG,
    }
    serialized = str(bundle.model_dump())
    assert "fixture-password" not in serialized
    assert "hidden-auth-token" not in serialized
    assert "private-token" not in serialized
    assert "4111 1111 1111 1111" not in serialized
    assert "[REDACTED_NUMBER]" in serialized
    assert "https://example.com/login" in serialized
    assert bundle.evidence[0].reference == "EXEC-001_20261001.png"
    assert repository.get_by_execution_id("EXEC-001") == bundle


def test_failure_analyzer_uses_structured_untrusted_evidence_and_valid_refs() -> None:
    settings = Settings(_env_file=None, max_failure_analysis_text=1000)
    evidence_repository = EvidenceRepository()
    application_execution = execution()
    application_execution.network_errors = []
    bundle = EvidenceCollector(evidence_repository, settings).collect_failure(case(), application_execution, "https://example.com/login")
    analysis = defect_analysis([bundle.evidence[0].id])
    client = FakeStructuredAI(analysis)
    analyzer = FailureAnalyzer(client, settings)

    result = asyncio.run(analyzer.analyze_failure("EXEC-001", bundle))

    assert result.classification is FailureClassification.APPLICATION_DEFECT
    assert client.requests[0][2] is FailureAnalysis
    assert "untrusted data" in client.requests[0][0]
    assert "fixture-password" not in client.requests[0][1]
    assert "private-token" not in client.requests[0][1]
    assert "4111 1111 1111 1111" not in client.requests[0][1]

    invalid_reference = defect_analysis(["EVID-UNKNOWN"])
    invalid_analyzer = FailureAnalyzer(FakeStructuredAI(invalid_reference), settings)
    with pytest.raises(ValueError, match="evidence"):
        asyncio.run(invalid_analyzer.analyze_failure("EXEC-001", bundle))


def test_bug_generator_builds_repro_steps_only_from_actions_and_gates_review() -> None:
    settings = Settings(_env_file=None)
    evidence_repository = EvidenceRepository()
    bundle = EvidenceCollector(evidence_repository, settings).collect_failure(case(), execution(), "https://example.com/login")
    draft = BugReportDraft(
        title="Required username validation message is not displayed",
        summary="Submitting the login form with an empty username showed no required-field message.",
        module="Login form validation",
        severity=BugSeverity.MEDIUM,
        priority=BugPriority.P2,
        possible_cause="Client-side required-field validation may not be triggering.",
    )
    client = FakeStructuredAI(draft)
    generator = BugGenerator(client, settings)

    report = asyncio.run(generator.generate_bug_report(
        "TEST-001", "https://example.com/login", case(), execution(),
        defect_analysis([item.id for item in bundle.evidence]), bundle,
    ))

    assert report.status is BugReportStatus.DRAFT
    assert report.classification is FailureClassification.APPLICATION_DEFECT
    assert report.evidence == [item.id for item in bundle.evidence]
    assert report.steps_to_reproduce == [
        "Open https://example.com/login.",
        "Fill the Password field using the configured test value.",
        "Click Login.",
    ]
    assert "fixture-password" not in str(report.model_dump())
    assert client.requests[0][2] is BugReportDraft

    class NoCallAI:
        async def generate_structured_response(self, *args: Any) -> Any:
            raise AssertionError("The AI must not be called for non-defect outcomes")

    review_generator = BugGenerator(NoCallAI(), settings)
    non_defect = FailureAnalysis(
        execution_id="EXEC-001", classification=FailureClassification.TEST_EXECUTION_ERROR,
        confidence=AnalysisConfidence.HIGH, summary="The target was not found.",
        expected_behavior="Username is required.", actual_behavior="The target could not be resolved.",
        evidence=[], possible_causes=[], recommended_next_step="Review the target name.", needs_review=True,
    )
    review_report = asyncio.run(review_generator.generate_bug_report(
        "TEST-001", "https://example.com/login", case(), execution(TestExecutionStatus.BLOCKED), non_defect, bundle,
    ))
    assert review_report.status is BugReportStatus.NEEDS_REVIEW
    assert review_report.priority is BugPriority.P2
    assert review_report.possible_cause == "Not established from the available evidence."


def test_network_or_authentication_failure_does_not_create_draft_defect() -> None:
    settings = Settings(_env_file=None)
    bundle = EvidenceCollector(EvidenceRepository(), settings).collect_failure(case(), execution(), "https://example.com/login")
    client = FakeStructuredAI()
    generator = BugGenerator(client, settings)
    analysis = FailureAnalysis(
        execution_id="EXEC-001", classification=FailureClassification.NETWORK_ERROR,
        confidence=AnalysisConfidence.MEDIUM, summary="The login request returned HTTP 500.",
        expected_behavior="The request should show username validation.", actual_behavior="The request returned HTTP 500.",
        evidence=[], possible_causes=["The backend or server environment may have failed."],
        recommended_next_step="Check server logs and retry in a known-good environment.", needs_review=True,
    )

    report = asyncio.run(generator.generate_bug_report("TEST-001", "https://example.com/login", case(), execution(), analysis, bundle))

    assert client.requests == []
    assert report.status is BugReportStatus.NEEDS_REVIEW
    assert report.classification is FailureClassification.NETWORK_ERROR


class FakeBugReportService:
    def __init__(self, analysis_repository, bug_repository, evidence_repository, analysis, report, bundle) -> None:
        self.analysis_repository = analysis_repository
        self.bug_repository = bug_repository
        self.evidence_repository = evidence_repository
        self.analysis = analysis
        self.report = report
        self.bundle = bundle

    async def analyze_execution(self, session_id: str, website_url: str, test_case: TestCase, result: TestExecutionResult):
        self.analysis_repository.create(self.analysis)
        self.bug_repository.create(session_id, self.report)
        self.evidence_repository.save_bundle(self.bundle)
        return self.analysis, self.report, self.bundle


def test_analysis_and_bug_report_apis_cover_missing_and_existing_results() -> None:
    settings = Settings(_env_file=None)
    client = TestClient(create_app(settings=settings))
    session = client.post("/api/test-sessions", json={
        "url": "https://example.com/login", "instruction": "Test login", "mode": "TEST",
    }).json()
    session_id = session["id"]
    plan = TestPlan(summary="Login", test_cases=[case()], warnings=[])
    client.app.state.test_plan_repository.create(session_id, plan)
    result = execution()
    result.session_id = session_id
    client.app.state.execution_repository.create_execution(result)

    missing_analysis = client.get(f"/api/test-executions/{result.id}/analysis")
    missing_report = client.get(f"/api/test-executions/{result.id}/bug-report")
    assert missing_analysis.status_code == 404
    assert missing_report.status_code == 404

    bundle = EvidenceCollector(client.app.state.evidence_repository, settings).collect_failure(case(), result, session["url"])
    analysis = defect_analysis([item.id for item in bundle.evidence])
    report = BugReportDraft(
        title="Required username validation is missing", summary="The message was absent.",
        module="Login form", severity=BugSeverity.MEDIUM, priority=BugPriority.P2,
        possible_cause="Client-side validation may not run.",
    )
    generated_report = asyncio.run(BugGenerator(FakeStructuredAI(report), settings).generate_bug_report(
        session_id, session["url"], case(), result, analysis, bundle,
    ))
    client.app.state.bug_report_service = FakeBugReportService(
        client.app.state.failure_analysis_repository,
        client.app.state.bug_report_repository,
        client.app.state.evidence_repository,
        analysis,
        generated_report,
        bundle,
    )

    analyzed = client.post(f"/api/test-executions/{result.id}/analyze")
    assert analyzed.status_code == 200
    assert analyzed.json()["analysis"]["classification"] == "APPLICATION_DEFECT"
    assert analyzed.json()["bug_report"]["status"] == "DRAFT"
    assert len(analyzed.json()["evidence"]) == len(bundle.evidence)
    assert client.get(f"/api/test-executions/{result.id}/analysis").status_code == 200
    assert client.get(f"/api/test-executions/{result.id}/bug-report").status_code == 200
    assert len(client.get(f"/api/test-sessions/{session_id}/bug-reports").json()) == 1

    passed = execution(TestExecutionStatus.PASSED)
    passed.session_id = session_id
    client.app.state.execution_repository.create_execution(passed)
    rejected = client.post(f"/api/test-executions/{passed.id}/analyze")
    assert rejected.status_code == 409
