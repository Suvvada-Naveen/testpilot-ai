from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.bug_reports.bug_report_repository import BugReportRepository
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.bug_report import BugReport
from app.services.test_session_service import TestSessionService

execution_router = APIRouter(prefix="/api/test-executions", tags=["bug reports"])
session_router = APIRouter(prefix="/api/test-sessions", tags=["bug reports"])


def get_bug_report_repository(request: Request) -> BugReportRepository:
    return request.app.state.bug_report_repository


def get_execution_repository(request: Request) -> ExecutionRepository:
    return request.app.state.execution_repository


def get_test_session_service(request: Request) -> TestSessionService:
    return request.app.state.test_session_service


@execution_router.get("/{execution_id}/bug-report", response_model=BugReport)
def get_bug_report(
    execution_id: str,
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
    bug_report_repository: BugReportRepository = Depends(get_bug_report_repository),
) -> BugReport:
    if execution_repository.get_by_id(execution_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test execution not found")
    report = bug_report_repository.get_by_execution_id(execution_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No bug report found for this execution")
    return report


@session_router.get("/{session_id}/bug-reports", response_model=list[BugReport])
def get_session_bug_reports(
    session_id: str,
    session_service: TestSessionService = Depends(get_test_session_service),
    bug_report_repository: BugReportRepository = Depends(get_bug_report_repository),
) -> list[BugReport]:
    if session_service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    return bug_report_repository.list_by_session_id(session_id)
