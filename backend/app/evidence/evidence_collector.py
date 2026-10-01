from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import SecretStr

from app.core.config import Settings
from app.core.sensitive_data import redact_sensitive_text, safe_url, sanitize_sensitive_data
from app.evidence.evidence_repository import EvidenceRepository
from app.schemas.evidence import Evidence, EvidenceType, FailureEvidenceBundle
from app.schemas.test_execution import TestExecutionResult
from app.schemas.test_plan import TestCase

def _safe_url(value: str) -> str:
    return safe_url(value)


def _mask_text(value: str, secrets: list[str]) -> str:
    return redact_sensitive_text(value, secrets)


def _sanitize(value: Any, secrets: list[str], key: str = "") -> Any:
    return sanitize_sensitive_data(value, secrets, key)


class EvidenceCollector:
    def __init__(self, repository: EvidenceRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def collect_failure(
        self,
        test_case: TestCase,
        execution: TestExecutionResult,
        website_url: str,
    ) -> FailureEvidenceBundle:
        secrets = [self._settings.test_credential_username or ""]
        if self._settings.test_credential_password is not None:
            secrets.append(self._settings.test_credential_password.get_secret_value())

        page_state = _sanitize(execution.actual_page_state, secrets)
        actions = _sanitize([action.model_dump(mode="json") for action in execution.actions], secrets)
        context: dict[str, object] = {
            "session_id": execution.session_id,
            "test_case": _sanitize(test_case.model_dump(mode="json"), secrets),
            "execution": {
                "execution_id": execution.id,
                "test_case_id": execution.test_case_id,
                "status": execution.status.value,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "duration": execution.duration,
                "expected_result": _mask_text(execution.expected_result[:1200], secrets),
                "actual_result": _mask_text(execution.actual_result[:12000], secrets),
                "failure_reason": _mask_text(execution.failure_reason or "", secrets),
                "actions": actions,
            },
            "website_url": _safe_url(website_url),
            "page_state": page_state,
            "console_errors": _sanitize(execution.console_errors[:20], secrets),
            "network_errors": _sanitize(execution.network_errors[:20], secrets),
        }

        now = execution.completed_at or datetime.now(UTC)
        records: list[Evidence] = []

        def add(evidence_type: EvidenceType, description: str, reference: str) -> None:
            if len(records) >= self._settings.max_failure_evidence_items:
                return
            records.append(Evidence(
                id=f"EVID-{uuid4().hex[:12].upper()}",
                execution_id=execution.id,
                type=evidence_type,
                description=_mask_text(description, secrets)[:1000],
                created_at=now,
                reference=reference,
            ))

        if execution.screenshot_id:
            add(EvidenceType.SCREENSHOT, "Final screenshot captured for the failed execution.", execution.screenshot_id)
        add(EvidenceType.PAGE_STATE, "Sanitized final page state.", f"{execution.id}:page-state")
        add(EvidenceType.ACTION_LOG, "Executed browser actions with input values omitted.", f"{execution.id}:actions")
        if isinstance(page_state, dict) and page_state.get("visible_text"):
            add(EvidenceType.PAGE_TEXT, "Visible text observed after the failed test.", f"{execution.id}:page-text")
        for index, error in enumerate(execution.console_errors[:20]):
            add(EvidenceType.CONSOLE_ERROR, _mask_text(error.get("text", "Console error")[:500], secrets), f"{execution.id}:console:{index}")
        for index, error in enumerate(execution.network_errors[:20]):
            add(EvidenceType.NETWORK_ERROR, _mask_text(error.get("failure", "Network request failed")[:500], secrets), f"{execution.id}:network:{index}")
        add(EvidenceType.EXECUTION_LOG, "Expected versus actual result and execution status.", f"{execution.id}:execution")

        bundle = FailureEvidenceBundle(execution_id=execution.id, evidence=records, context=context)
        return self._repository.save_bundle(bundle)
