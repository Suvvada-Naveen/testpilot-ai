import logging

from app.analysis.bug_generator import BugGenerator
from app.analysis.failure_analyzer import FailureAnalyzer
from app.analysis.failure_analysis_repository import FailureAnalysisRepository
from app.evidence.evidence_collector import EvidenceCollector
from app.evidence.evidence_repository import EvidenceRepository
from app.bug_reports.bug_report_repository import BugReportRepository
from app.schemas.bug_report import BugReport
from app.schemas.evidence import FailureEvidenceBundle
from app.schemas.failure_analysis import FailureAnalysis
from app.schemas.test_execution import TestExecutionResult
from app.schemas.test_plan import TestCase

logger = logging.getLogger(__name__)


class BugReportService:
    def __init__(
        self,
        failure_analyzer: FailureAnalyzer,
        bug_generator: BugGenerator,
        evidence_collector: EvidenceCollector,
        evidence_repository: EvidenceRepository,
        analysis_repository: FailureAnalysisRepository,
        bug_report_repository: BugReportRepository,
    ) -> None:
        self._failure_analyzer = failure_analyzer
        self._bug_generator = bug_generator
        self._evidence_collector = evidence_collector
        self._evidence_repository = evidence_repository
        self._analysis_repository = analysis_repository
        self._bug_report_repository = bug_report_repository

    async def analyze_execution(
        self,
        session_id: str,
        website_url: str,
        test_case: TestCase,
        execution: TestExecutionResult,
    ) -> tuple[FailureAnalysis, BugReport, FailureEvidenceBundle]:
        bundle = self._evidence_repository.get_by_execution_id(execution.id)
        if bundle is None:
            bundle = self._evidence_collector.collect_failure(test_case, execution, website_url)

        analysis = await self._failure_analyzer.analyze_failure(execution.id, bundle)
        report = await self._bug_generator.generate_bug_report(
            session_id,
            website_url,
            test_case,
            execution,
            analysis,
            bundle,
        )
        saved_analysis = self._analysis_repository.create(analysis)
        saved_report = self._bug_report_repository.create(session_id, report)
        logger.info(
            "failure analysis stored session_id=%s execution_id=%s classification=%s report_status=%s",
            session_id,
            execution.id,
            saved_analysis.classification.value,
            saved_report.status.value,
        )
        return saved_analysis, saved_report, bundle
