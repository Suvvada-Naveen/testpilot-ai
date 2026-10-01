import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.browser.screenshot_manager import SCREENSHOTS_DIR
from app.execution.execution_service import ExecutionService
from app.models.test_session import TestSession
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.test_plan_repository import TestPlanRepository
from app.schemas.test_execution import (
    ExecuteTestCaseRequest,
    ExecuteTestsRequest,
    ExecutionBatchResponse,
    TestExecutionResult,
    TestExecutionStatus,
)
from app.schemas.test_plan import TestCase
from app.services.test_session_service import TestSessionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/test-sessions", tags=["test executions"])


def get_test_session_service(request: Request) -> TestSessionService:
    return request.app.state.test_session_service


def get_test_plan_repository(request: Request) -> TestPlanRepository:
    return request.app.state.test_plan_repository


def get_execution_repository(request: Request) -> ExecutionRepository:
    return request.app.state.execution_repository


def get_execution_service(request: Request) -> ExecutionService:
    return request.app.state.execution_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _get_session_plan(
    session_id: str,
    session_service: TestSessionService,
    plan_repository: TestPlanRepository,
) -> tuple[TestSession, list[TestCase]]:
    session = session_service.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    plan = plan_repository.get_by_session_id(session_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No test plan has been generated")
    if not plan.test_cases:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The test plan contains no executable test cases")
    return session, plan.test_cases


@router.post("/{session_id}/execute", response_model=ExecutionBatchResponse)
async def execute_selected_tests(
    session_id: str,
    payload: ExecuteTestsRequest = ExecuteTestsRequest(),
    session_service: TestSessionService = Depends(get_test_session_service),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
    execution_service: ExecutionService = Depends(get_execution_service),
    settings: Settings = Depends(get_settings),
) -> ExecutionBatchResponse:
    session, plan_cases = _get_session_plan(session_id, session_service, plan_repository)
    by_id = {test_case.id: test_case for test_case in plan_cases}
    selected_ids = payload.test_case_ids or list(by_id)
    if len(selected_ids) > settings.max_test_cases_per_execution:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A maximum of {settings.max_test_cases_per_execution} test cases can be executed at once",
        )
    missing_ids = [test_case_id for test_case_id in selected_ids if test_case_id not in by_id]
    if missing_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more selected test cases were not found")

    results: list[TestExecutionResult] = []
    for test_case_id in selected_ids:
        results.append(await execution_service.execute_test_case(
            session_id,
            by_id[test_case_id],
            session.url,
            confirm_destructive=payload.confirm_destructive,
        ))

    if all(result.status == TestExecutionStatus.PASSED for result in results):
        overall_status = "PASSED"
    elif any(result.status == TestExecutionStatus.FAILED for result in results):
        overall_status = "FAILED"
    elif all(result.status == TestExecutionStatus.BLOCKED for result in results):
        overall_status = "BLOCKED"
    else:
        overall_status = "PARTIAL"
    return ExecutionBatchResponse(
        session_id=session_id,
        status=overall_status,
        total=len(results),
        execution_ids=[result.id for result in results],
        executions=results,
    )


@router.post("/{session_id}/test-cases/{test_case_id}/execute", response_model=TestExecutionResult)
async def execute_single_test(
    session_id: str,
    test_case_id: str,
    payload: ExecuteTestCaseRequest = ExecuteTestCaseRequest(),
    session_service: TestSessionService = Depends(get_test_session_service),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> TestExecutionResult:
    session, plan_cases = _get_session_plan(session_id, session_service, plan_repository)
    test_case = next((case for case in plan_cases if case.id == test_case_id), None)
    if test_case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    return await execution_service.execute_test_case(
        session_id,
        test_case,
        session.url,
        confirm_destructive=payload.confirm_destructive,
    )


@router.get("/{session_id}/executions", response_model=list[TestExecutionResult])
def get_session_executions(
    session_id: str,
    session_service: TestSessionService = Depends(get_test_session_service),
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
) -> list[TestExecutionResult]:
    if session_service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    return execution_repository.get_session_executions(session_id)


@router.get("/{session_id}/executions/{execution_id}", response_model=TestExecutionResult)
def get_execution(
    session_id: str,
    execution_id: str,
    session_service: TestSessionService = Depends(get_test_session_service),
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
) -> TestExecutionResult:
    if session_service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    execution = execution_repository.get_execution(session_id, execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test execution not found")
    return execution


@router.get("/{session_id}/executions/{execution_id}/screenshot")
def get_execution_screenshot(
    session_id: str,
    execution_id: str,
    session_service: TestSessionService = Depends(get_test_session_service),
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
) -> FileResponse:
    if session_service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    execution = execution_repository.get_execution(session_id, execution_id)
    if execution is None or not execution.screenshot_id or Path(execution.screenshot_id).name != execution.screenshot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution screenshot not found")
    screenshot_path = SCREENSHOTS_DIR / execution.screenshot_id
    if not screenshot_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution screenshot not found")
    return FileResponse(screenshot_path, media_type="image/png")
