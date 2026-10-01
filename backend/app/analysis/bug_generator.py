import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.ai.ai_client import AIClient
from app.analysis.prompts import BUG_DRAFT_PROMPT, bug_draft_message
from app.core.config import Settings
from app.schemas.bug_report import (
    BugPriority,
    BugReport,
    BugReportDraft,
    BugReportStatus,
    BugSeverity,
)
from app.schemas.evidence import FailureEvidenceBundle
from app.schemas.failure_analysis import AnalysisConfidence, FailureAnalysis, FailureClassification
from app.schemas.test_execution import TestExecutionResult
from app.schemas.test_plan import TestCase

logger = logging.getLogger(__name__)


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return ""


def _reproduction_steps(test_case: TestCase, execution: TestExecutionResult) -> list[str]:
    steps: list[str] = []
    for action in execution.actions:
        target = action.target or ""
        if action.action.value == "navigate":
            steps.append(f"Open {_safe_url(target) or 'the tested page'}.")
        elif action.action.value == "click":
            steps.append(f"Click {target or 'the identified control'}.")
        elif action.action.value == "fill":
            steps.append(f"Fill the {target or 'identified field'} using the configured test value.")
        elif action.action.value == "select":
            steps.append(f"Select an option in {target or 'the identified select field'}.")
        elif action.action.value == "check":
            steps.append(f"Check {target or 'the identified checkbox'}.")
        elif action.action.value == "uncheck":
            steps.append(f"Uncheck {target or 'the identified checkbox'}.")
        elif action.action.value == "press":
            steps.append(f"Press the approved key on {target or 'the focused control'}.")
        elif action.action.value == "scroll":
            steps.append("Scroll the page.")
        elif action.action.value == "wait":
            steps.append("Wait for the page to update.")
        elif action.action.value == "read_page":
            steps.append("Observe the resulting page state.")
        elif action.action.value == "take_screenshot":
            steps.append("Capture the current page screenshot.")
    return steps or [f"Run the generated test case: {test_case.title}."]


class BugGenerator:
    def __init__(self, ai_client: AIClient, settings: Settings) -> None:
        self._ai_client = ai_client
        self._settings = settings

    async def generate_bug_report(
        self,
        session_id: str,
        website_url: str,
        test_case: TestCase,
        execution: TestExecutionResult,
        analysis: FailureAnalysis,
        evidence_bundle: FailureEvidenceBundle,
    ) -> BugReport:
        eligible = (
            analysis.classification == FailureClassification.APPLICATION_DEFECT
            and analysis.confidence in {AnalysisConfidence.HIGH, AnalysisConfidence.MEDIUM}
            and not analysis.needs_review
        )
        evidence_ids = [item.id for item in evidence_bundle.evidence]
        context: Mapping[str, object] = evidence_bundle.context

        if eligible:
            draft = await self._ai_client.generate_structured_response(
                BUG_DRAFT_PROMPT,
                bug_draft_message(
                    analysis.model_dump(mode="json"),
                    context,
                    self._settings.max_failure_analysis_text,
                ),
                BugReportDraft,
            )
            title = draft.title
            summary = draft.summary
            module = draft.module
            severity = draft.severity
            priority = draft.priority
            possible_cause = f"Hypothesis: {draft.possible_cause}"
            report_status = BugReportStatus.DRAFT
        else:
            title = f"Failure needs review: {test_case.title}"[:200]
            summary = analysis.summary
            module = "Not identified"
            severity = BugSeverity.MEDIUM
            priority = BugPriority.P2
            possible_cause = "Not established from the available evidence."
            report_status = BugReportStatus.NEEDS_REVIEW

        page_state = context.get("page_state", {})
        if not isinstance(page_state, Mapping):
            page_state = {}
        page_title = page_state.get("title", "")
        report = BugReport(
            id=f"BUG-{uuid4().hex[:10].upper()}",
            execution_id=execution.id,
            title=title,
            summary=summary,
            module=module,
            severity=severity,
            priority=priority,
            environment=f"{self._settings.app_env}; Chromium headless={self._settings.browser_headless}",
            url=_safe_url(website_url),
            preconditions=test_case.preconditions,
            steps_to_reproduce=_reproduction_steps(test_case, execution),
            expected_result=execution.expected_result,
            actual_result=execution.actual_result,
            evidence=evidence_ids,
            observed_behavior=analysis.actual_behavior,
            possible_cause=possible_cause,
            classification=analysis.classification,
            status=report_status,
            created_at=datetime.now(UTC),
        )
        logger.info(
            "bug report prepared session_id=%s execution_id=%s status=%s evidence_count=%s page_title_present=%s",
            session_id,
            execution.id,
            report.status.value,
            len(report.evidence),
            bool(page_title),
        )
        return report
