import logging
import re
from collections.abc import Mapping
from typing import Any

from app.ai.ai_client import AIClient
from app.analysis.prompts import FAILURE_ANALYSIS_PROMPT, failure_analysis_message
from app.core.config import Settings
from app.schemas.evidence import FailureEvidenceBundle
from app.schemas.failure_analysis import AnalysisConfidence, FailureAnalysis, FailureClassification

logger = logging.getLogger(__name__)


class FailureAnalyzer:
    def __init__(self, ai_client: AIClient, settings: Settings) -> None:
        self._ai_client = ai_client
        self._settings = settings

    async def analyze_failure(
        self,
        execution_id: str,
        evidence_bundle: FailureEvidenceBundle,
    ) -> FailureAnalysis:
        context: Mapping[str, Any] = evidence_bundle.context
        analysis = await self._ai_client.generate_structured_response(
            FAILURE_ANALYSIS_PROMPT,
            failure_analysis_message(
                context,
                [item.id for item in evidence_bundle.evidence],
                self._settings.max_failure_analysis_text,
            ),
            FailureAnalysis,
        )
        if analysis.execution_id != execution_id:
            raise ValueError("Analysis response execution ID did not match the requested execution")
        execution = context.get("execution", {})
        execution_status = execution.get("status") if isinstance(execution, Mapping) else None
        network_errors = context.get("network_errors", [])
        http_statuses = {
            int(match.group(1))
            for item in network_errors if isinstance(item, Mapping)
            for match in [re.search(r"\bHTTP\s+(\d{3})\b", str(item.get("failure", "")), re.IGNORECASE)]
            if match is not None
        } if isinstance(network_errors, list) else set()
        if analysis.classification == FailureClassification.APPLICATION_DEFECT and execution_status == "BLOCKED":
            analysis = analysis.model_copy(update={
                "classification": FailureClassification.TEST_EXECUTION_ERROR,
                "confidence": AnalysisConfidence.HIGH,
                "summary": "The test execution was blocked before it could establish application behavior.",
                "possible_causes": [],
                "recommended_next_step": "Resolve the test execution blocker and rerun the case before assessing application behavior.",
                "needs_review": True,
            })
        elif analysis.classification == FailureClassification.APPLICATION_DEFECT and any(code >= 500 for code in http_statuses):
            analysis = analysis.model_copy(update={
                "classification": FailureClassification.NETWORK_ERROR,
                "confidence": AnalysisConfidence.HIGH,
                "summary": "A server response returned HTTP 5xx; the available evidence does not identify which component caused it.",
                "possible_causes": [],
                "recommended_next_step": "Review server-side logs and rerun in a known-good environment before assigning a component owner.",
                "needs_review": True,
            })
        elif analysis.classification == FailureClassification.APPLICATION_DEFECT and http_statuses.intersection({401, 403}):
            analysis = analysis.model_copy(update={
                "classification": FailureClassification.AUTHENTICATION_ERROR,
                "confidence": AnalysisConfidence.HIGH,
                "summary": "The request returned an authentication/authorization response; the available evidence does not establish an application defect.",
                "possible_causes": [],
                "recommended_next_step": "Verify the test account and authentication state, then rerun the case.",
                "needs_review": True,
            })
        elif analysis.classification == FailureClassification.APPLICATION_DEFECT and not analysis.evidence:
            analysis = analysis.model_copy(update={
                "classification": FailureClassification.AMBIGUOUS,
                "confidence": AnalysisConfidence.LOW,
                "summary": "The available evidence references do not directly establish an application behavior failure.",
                "possible_causes": [],
                "recommended_next_step": "Collect direct page evidence for the expected behavior before filing a defect.",
                "needs_review": True,
            })
        if analysis.classification.value == "AMBIGUOUS" and not analysis.needs_review:
            raise ValueError("Ambiguous failure analyses must require review")
        allowed_evidence_ids = {item.id for item in evidence_bundle.evidence}
        if any(reference not in allowed_evidence_ids for reference in analysis.evidence):
            raise ValueError("Analysis referenced evidence that was not collected")
        logger.info(
            "failure analysis completed execution_id=%s classification=%s confidence=%s needs_review=%s",
            execution_id,
            analysis.classification.value,
            analysis.confidence.value,
            analysis.needs_review,
        )
        return analysis
