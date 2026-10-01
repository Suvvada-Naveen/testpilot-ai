import logging
from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.ai_client import AIClient
from app.agent.action_planner import ActionPlanner
from app.agent.result_evaluator import ResultEvaluator
from app.api.routes import executions, health, tests
from app.core.config import Settings
from app.execution.execution_service import ExecutionService
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.test_plan_repository import TestPlanRepository
from app.repositories.test_session_repository import TestSessionRepository
from app.services.test_session_service import TestSessionService
from app.ai.testing_agent import TestingAgent

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    repository: TestSessionRepository | None = None,
    test_plan_repository: TestPlanRepository | None = None,
    testing_agent: TestingAgent | None = None,
    execution_repository: ExecutionRepository | None = None,
    execution_service: ExecutionService | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    app_repository = repository or TestSessionRepository()
    app_test_plan_repository = test_plan_repository or TestPlanRepository()
    app_execution_repository = execution_repository or ExecutionRepository()
    ai_client = AIClient(app_settings)
    app = FastAPI(title="TestPilot AI API", version="2.0.0")
    app.state.settings = app_settings
    app.state.test_session_repository = app_repository
    app.state.test_session_service = TestSessionService(app_repository)
    app.state.test_plan_repository = app_test_plan_repository
    app.state.testing_agent = testing_agent or TestingAgent(ai_client, app_settings)
    app.state.execution_repository = app_execution_repository
    app.state.execution_service = execution_service or ExecutionService(
        app_execution_repository,
        ActionPlanner(ai_client),
        ResultEvaluator(ai_client),
        app_settings,
    )

    origins: Sequence[str] = tuple(dict.fromkeys((
        app_settings.frontend_url.rstrip("/"),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unexpected error while handling %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(tests.router)
    app.include_router(executions.router)
    return app


app = create_app()