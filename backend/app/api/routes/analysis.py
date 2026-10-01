import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.ai.ai_client import AIServiceError
from app.bug_reports.bug_report_service import BugReportService
from app.execution.execution_service import ExecutionService
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.test_plan_repository import TestPlanRepository
from app.schemas.evidence import FailureEvidenceBundle
from app.schemas.failure_analysis import FailureAnalysis
from app.schemas.failure_analysis_response import FailureAnalysisResponse
from app.schemas.test_execution import TestExecutionResult, TestExecutionStatus
from app.services.test_session_service import TestSessionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/test-executions", tags=["failure analysis"])


def get_test_session_service(request: Request) -> TestSessionService:
    return request.app.state.test_session_service


def get_execution_repository(request: Request) -> ExecutionRepository:
    return request.app.state.execution_repository


def get_test_plan_repository(request: Request) -> TestPlanRepository:
    return request.app.state.test_plan_repository


def get_analysis_repository(request: Request):
    return request.app.state.failure_analysis_repository


def get_evidence_repository(request: Request):
    return request.app.state.evidence_repository


def get_bug_report_service(request: Request) -> BugReportService:
    return request.app.state.bug_report_service


def get_execution_service(request: Request) -> ExecutionService:
    return request.app.state.execution_service


def _get_execution(execution_id: str, repository: ExecutionRepository) -> TestExecutionResult:
    execution = repository.get_by_id(execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test execution not found")
    return execution


@router.post("/{execution_id}/analyze", response_model=FailureAnalysisResponse)
async def analyze_execution(
    execution_id: str,
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
    session_service: TestSessionService = Depends(get_test_session_service),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
    bug_report_service: BugReportService = Depends(get_bug_report_service),
) -> FailureAnalysisResponse:
    execution = _get_execution(execution_id, execution_repository)
    if execution.status not in {TestExecutionStatus.FAILED, TestExecutionStatus.BLOCKED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed or blocked executions can be analyzed")
    session = session_service.get(execution.session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    plan = plan_repository.get_by_session_id(execution.session_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No test plan has been generated")
    test_case = next((case for case in plan.test_cases if case.id == execution.test_case_id), None)
    if test_case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    try:
        analysis, bug_report, evidence = await bug_report_service.analyze_execution(
            execution.session_id,
            session.url,
            test_case,
            execution,
        )
    except AIServiceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failure analysis is temporarily unavailable. Please try again.",
        ) from None
    except Exception as error:
        logger.warning("failure analysis failed execution_id=%s error_type=%s", execution_id, type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failure analysis is temporarily unavailable. Please try again.",
        ) from None
    return FailureAnalysisResponse(analysis=analysis, bug_report=bug_report, evidence=evidence.evidence)


@router.get("/{execution_id}/analysis", response_model=FailureAnalysis)
def get_failure_analysis(
    execution_id: str,
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
    analysis_repository=Depends(get_analysis_repository),
) -> FailureAnalysis:
    _get_execution(execution_id, execution_repository)
    analysis = analysis_repository.get_by_execution_id(execution_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No failure analysis found for this execution")
    return analysis


@router.get("/{execution_id}/evidence", response_model=FailureEvidenceBundle)
def get_execution_evidence(
    execution_id: str,
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
    evidence_repository=Depends(get_evidence_repository),
) -> FailureEvidenceBundle:
    _get_execution(execution_id, execution_repository)
    bundle = evidence_repository.get_by_execution_id(execution_id)
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No failure evidence found for this execution")
    return bundle
