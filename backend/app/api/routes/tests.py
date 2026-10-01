from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from app.ai.ai_client import AIServiceError, MissingAPIKeyError
from app.browser.screenshot_manager import SCREENSHOTS_DIR
from app.core.config import Settings
from app.models.test_session import TestSession, TestStatus
from app.schemas.browser_inspection import BrowserInspectionResponse
from app.schemas.test_plan import TestPlan
from app.schemas.test_session import CreateTestSessionRequest, TestSessionResponse
from app.repositories.test_plan_repository import TestPlanRepository
from app.repositories.execution_repository import ExecutionRepository
from app.services.browser_test_service import BrowserInspectionError, UrlValidationError, inspect_website
from app.services.test_session_service import SessionValidationError, TestSessionService
from app.ai.testing_agent import TestingAgent

router = APIRouter(prefix="/api/test-sessions", tags=["test sessions"])


def get_test_session_service(request: Request) -> TestSessionService:
    return request.app.state.test_session_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_testing_agent(request: Request) -> TestingAgent:
    return request.app.state.testing_agent


def get_test_plan_repository(request: Request) -> TestPlanRepository:
    return request.app.state.test_plan_repository


def get_execution_repository(request: Request) -> ExecutionRepository:
    return request.app.state.execution_repository


@router.post("", response_model=TestSessionResponse, status_code=status.HTTP_201_CREATED)
def create_test_session(
    payload: CreateTestSessionRequest,
    service: TestSessionService = Depends(get_test_session_service),
) -> TestSession:
    try:
        return service.create(payload)
    except SessionValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.get("", response_model=list[TestSessionResponse])
def get_test_sessions(
    service: TestSessionService = Depends(get_test_session_service),
) -> list[TestSession]:
    return service.list()


@router.get("/{session_id}", response_model=TestSessionResponse)
def get_test_session(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
) -> TestSession:
    session = service.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_session(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
    execution_repository: ExecutionRepository = Depends(get_execution_repository),
) -> Response:
    if not service.delete(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    plan_repository.delete_by_session_id(session_id)
    execution_repository.delete_session_executions(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/inspect", response_model=BrowserInspectionResponse)
async def inspect_test_session(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    session = service.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    if session.status == TestStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This testing session is already being inspected")

    service.update_status(session_id, TestStatus.RUNNING)
    try:
        result = await inspect_website(session.url, session_id, settings)
    except (UrlValidationError, BrowserInspectionError) as error:
        result = {
            "session_id": session_id,
            "status": "FAILED",
            "page": {"requested_url": session.url, "final_url": "", "status_code": None, "title": ""},
            "elements": {
                "headings": [], "buttons": [], "inputs": [], "links": [], "forms": [],
                "checkboxes": [], "radio_buttons": [], "selects": [],
            },
            "visible_text": "",
            "screenshot_id": "",
            "console_errors": [],
            "console_messages": [],
            "network_errors": [],
            "error": str(error),
        }
        service.update_status(session_id, TestStatus.FAILED)
        service.save_inspection(session_id, result)
        return result
    except Exception:
        service.update_status(session_id, TestStatus.FAILED)
        result = {
            "session_id": session_id,
            "status": "FAILED",
            "page": {"requested_url": session.url, "final_url": "", "status_code": None, "title": ""},
            "elements": {
                "headings": [], "buttons": [], "inputs": [], "links": [], "forms": [],
                "checkboxes": [], "radio_buttons": [], "selects": [],
            },
            "visible_text": "",
            "screenshot_id": "",
            "console_errors": [],
            "console_messages": [],
            "network_errors": [],
            "error": "Unable to inspect this website due to a browser error.",
        }
        service.save_inspection(session_id, result)
        return result

    service.update_status(session_id, TestStatus.COMPLETED)
    service.save_inspection(session_id, result)
    return result


@router.get("/{session_id}/inspection", response_model=BrowserInspectionResponse)
def get_test_session_inspection(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
) -> dict[str, object]:
    if service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    result = service.get_inspection(session_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No inspection found for this testing session",
        )
    return result


@router.get("/{session_id}/inspection/screenshot")
def get_test_session_screenshot(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
) -> FileResponse:
    result = service.get_inspection(session_id)
    if result is None or service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    screenshot_id = result.get("screenshot_id")
    if not isinstance(screenshot_id, str) or not screenshot_id or Path(screenshot_id).name != screenshot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    screenshot_path = SCREENSHOTS_DIR / screenshot_id
    if not screenshot_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return FileResponse(screenshot_path, media_type="image/png")


@router.post("/{session_id}/generate-tests", response_model=TestPlan)
async def generate_test_plan(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
    testing_agent: TestingAgent = Depends(get_testing_agent),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
) -> TestPlan:
    session = service.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    inspection = service.get_inspection(session_id)
    if inspection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website inspection is required before generating tests",
        )
    if inspection.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A successful website inspection is required before generating tests",
        )

    try:
        plan = await testing_agent.generate_test_plan(session_id, session.instruction, inspection)
    except MissingAPIKeyError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
    except AIServiceError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI test generation is temporarily unavailable. Please try again.",
        ) from None

    return plan_repository.create(session_id, plan)


@router.get("/{session_id}/test-plan", response_model=TestPlan)
def get_test_plan(
    session_id: str,
    service: TestSessionService = Depends(get_test_session_service),
    plan_repository: TestPlanRepository = Depends(get_test_plan_repository),
) -> TestPlan:
    if service.get(session_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testing session not found")
    plan = plan_repository.get_by_session_id(session_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No test plan has been generated")
    return plan