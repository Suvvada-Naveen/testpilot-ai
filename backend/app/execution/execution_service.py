import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from playwright.async_api import Page, Request

from app.agent.action_planner import ActionPlanner
from app.agent.result_evaluator import ResultEvaluator
from app.browser.browser_manager import BrowserManager
from app.browser.browser_tools import BrowserToolError, BrowserTools, CredentialProvider, MockCredentialProvider
from app.browser.page_reader import read_page
from app.browser.screenshot_manager import ScreenshotManager
from app.core.config import Settings
from app.repositories.execution_repository import ExecutionRepository
from app.schemas.browser_action import BrowserAction, BrowserToolName, EvaluationStatus
from app.schemas.test_execution import ActionExecution, ActionExecutionStatus, TestExecutionResult, TestExecutionStatus
from app.schemas.test_plan import TestCase

logger = logging.getLogger(__name__)


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        netloc = f"[{host}]" if ":" in host else host
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[invalid URL]"


class ExecutionService:
    def __init__(
        self,
        repository: ExecutionRepository,
        action_planner: ActionPlanner,
        result_evaluator: ResultEvaluator,
        settings: Settings,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        self._repository = repository
        self._action_planner = action_planner
        self._result_evaluator = result_evaluator
        self._settings = settings
        self._credential_provider = credential_provider or MockCredentialProvider(settings)

    async def execute_test_case(
        self,
        session_id: str,
        test_case: TestCase,
        url: str,
        confirm_destructive: bool = False,
    ) -> TestExecutionResult:
        started_at = datetime.now(UTC)
        started_clock = time.perf_counter()
        result = TestExecutionResult(
            id=f"EXEC-{uuid4().hex[:12].upper()}",
            session_id=session_id,
            test_case_id=test_case.id,
            status=TestExecutionStatus.RUNNING,
            started_at=started_at,
            duration=0,
            expected_result=test_case.expected_result,
        )
        self._repository.create_execution(result)
        logger.info("test execution started session_id=%s execution_id=%s test_case_id=%s", session_id, result.id, test_case.id)

        manager = BrowserManager(headless=self._settings.browser_headless)
        page: Page | None = None
        tools: BrowserTools | None = None
        page_state: dict[str, Any] = {"url": _safe_url(url), "visible_text": "", "title": ""}
        action_history: list[dict[str, Any]] = []
        action_results: list[dict[str, Any]] = []
        console_errors: list[dict[str, str]] = []
        network_errors: list[dict[str, str]] = []
        secrets = self._configured_secrets()

        def mask(value: str) -> str:
            for secret in secrets:
                if secret:
                    value = value.replace(secret, "********")
            return value

        def capture_console(message: Any) -> None:
            if getattr(message, "type", "") == "error" and len(console_errors) < self._settings.max_console_messages:
                console_errors.append({"type": "error", "text": mask(str(getattr(message, "text", ""))[:2000])})

        def capture_request_failure(request: Request) -> None:
            if len(network_errors) < self._settings.max_console_messages:
                network_errors.append({
                    "url": _safe_url(request.url),
                    "method": request.method,
                    "failure": mask(str(request.failure or "Request failed")[:500]),
                })

        try:
            await manager.start()
            await manager.create_context()
            page = await manager.create_page()
            page.set_default_timeout(self._settings.action_timeout)
            tools = BrowserTools(
                page,
                self._settings,
                result.id,
                url,
                self._credential_provider,
                confirm_destructive=confirm_destructive,
                requires_credentials=test_case.requires_credentials,
            )
            page.on("console", capture_console)
            page.on("requestfailed", capture_request_failure)
            await page.route("**/*", tools.guard_request)

            navigate = BrowserAction(
                action=BrowserToolName.NAVIGATE,
                target=url,
                reason="Open the approved testing website.",
            )
            await self._execute_action(result, tools, navigate, action_history, action_results, mask)
            page_state = await self._read_safe_page(page, mask)

            while len(result.actions) < self._settings.max_actions_per_test:
                action = await self._action_planner.next_action(test_case, page_state, action_history, action_results)
                if not isinstance(action, BrowserAction):
                    action = BrowserAction.model_validate(action)
                await self._execute_action(result, tools, action, action_history, action_results, mask)
                if tools.restricted_request:
                    self._finish(
                        result, TestExecutionStatus.BLOCKED,
                        "A browser request was blocked by the network safety policy.",
                        page_state, started_clock, console_errors, network_errors,
                    )
                    break

                tool_result = action_results[-1].get("observation")
                if action.action == BrowserToolName.READ_PAGE and isinstance(tool_result, dict):
                    page_state = self._mask_page_state(tool_result, mask)
                else:
                    page_state = await self._read_safe_page(page, mask)
                evaluation = await self._result_evaluator.evaluate(
                    test_case,
                    page_state,
                    action_history,
                    console_errors,
                    network_errors,
                )
                if evaluation.finished:
                    if evaluation.status == EvaluationStatus.PASS:
                        observed_state = json.dumps(page_state, ensure_ascii=True, sort_keys=True).casefold()
                        if not evaluation.evidence or any(evidence.casefold() not in observed_state for evidence in evaluation.evidence):
                            self._finish(
                                result,
                                TestExecutionStatus.BLOCKED,
                                "The evaluator did not provide verifiable page evidence for PASS.",
                                page_state,
                                started_clock,
                                console_errors,
                                network_errors,
                            )
                        else:
                            self._finish(result, TestExecutionStatus.PASSED, evaluation.reason, page_state, started_clock, console_errors, network_errors)
                    elif evaluation.status == EvaluationStatus.FAIL:
                        self._finish(result, TestExecutionStatus.FAILED, evaluation.reason, page_state, started_clock, console_errors, network_errors)
                    else:
                        self._finish(result, TestExecutionStatus.BLOCKED, evaluation.reason, page_state, started_clock, console_errors, network_errors)
                    break
                if evaluation.status != EvaluationStatus.CONTINUE:
                    self._finish(result, TestExecutionStatus.BLOCKED, "The evaluator returned an inconsistent progress state.", page_state, started_clock, console_errors, network_errors)
                    break
                self._repository.update_execution(result)
            else:
                self._finish(
                    result,
                    TestExecutionStatus.BLOCKED,
                    "Maximum browser action limit reached.",
                    page_state,
                    started_clock,
                    console_errors,
                    network_errors,
                )
        except BrowserToolError as error:
            self._finish(result, TestExecutionStatus.BLOCKED, str(error), page_state, started_clock, console_errors, network_errors)
        except Exception as error:
            logger.warning(
                "test execution stopped session_id=%s execution_id=%s error_type=%s",
                session_id,
                result.id,
                type(error).__name__,
            )
            reason = "AI execution service is unavailable." if page is None else "Test execution stopped because a browser or AI error occurred."
            self._finish(result, TestExecutionStatus.BLOCKED, reason, page_state, started_clock, console_errors, network_errors)
        finally:
            if page is not None:
                try:
                    result.screenshot_id = await ScreenshotManager().capture(page, result.id)
                except Exception as error:
                    logger.warning("execution screenshot capture failed execution_id=%s error_type=%s", result.id, type(error).__name__)
                    if result.status == TestExecutionStatus.PASSED:
                        result.status = TestExecutionStatus.BLOCKED
                        result.failure_reason = "Final screenshot evidence could not be captured."
            result.console_errors = console_errors
            result.network_errors = network_errors
            if result.completed_at is None:
                self._finish(result, TestExecutionStatus.BLOCKED, "Test execution did not complete.", page_state, started_clock, console_errors, network_errors)
            self._repository.update_execution(result)
            try:
                await manager.close_page(page)
            finally:
                await manager.close()

        logger.info(
            "test execution completed session_id=%s execution_id=%s test_case_id=%s status=%s actions=%s",
            session_id,
            result.id,
            test_case.id,
            result.status.value,
            len(result.actions),
        )
        return result

    async def _execute_action(
        self,
        result: TestExecutionResult,
        tools: BrowserTools,
        action: BrowserAction,
        action_history: list[dict[str, Any]],
        action_results: list[dict[str, Any]],
        mask: Any,
    ) -> None:
        started = time.perf_counter()
        try:
            observation = await tools.execute_browser_action(action)
            status = ActionExecutionStatus.SUCCESS
            error_message = None
        except BrowserToolError as error:
            observation = None
            status = ActionExecutionStatus.FAILED
            error_message = mask(str(error))[:1000]
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        safe_target = mask(_safe_url(action.target) if action.action == BrowserToolName.NAVIGATE and action.target else action.target or "")
        execution_action = ActionExecution(
            step=len(result.actions) + 1,
            action=action.action,
            target=safe_target or None,
            status=status,
            duration_ms=duration_ms,
            error=error_message,
        )
        result.actions.append(execution_action)
        action_history.append({
            "step": execution_action.step,
            "action": action.action.value,
            "target": safe_target,
            "status": status.value,
        })
        safe_observation = self._safe_ai_observation(observation, mask)
        action_results.append({
            "step": execution_action.step,
            "status": status.value,
            "observation": safe_observation,
            "error": error_message,
        })
        self._repository.update_execution(result)
        if status == ActionExecutionStatus.FAILED:
            raise BrowserToolError(error_message or "Browser action failed.")

    async def _read_safe_page(self, page: Page, mask: Any) -> dict[str, Any]:
        state = await read_page(page, self._settings.max_page_text_length)
        return self._mask_page_state(state, mask)

    @staticmethod
    def _mask_page_state(state: dict[str, Any], mask: Any) -> dict[str, Any]:
        safe_state = dict(state)
        for key in ("url", "title", "visible_text"):
            value = safe_state.get(key)
            if isinstance(value, str):
                safe_state[key] = mask(_safe_url(value) if key == "url" else value)
        elements = safe_state.get("elements", {})
        if isinstance(elements, dict):
            for collection in ("links", "forms"):
                for item in elements.get(collection, []):
                    if isinstance(item, dict):
                        key = "href" if collection == "links" else "action"
                        if isinstance(item.get(key), str):
                            item[key] = _safe_url(item[key])
        return safe_state

    @staticmethod
    def _safe_ai_observation(value: Any, mask: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {
                item_key: ExecutionService._safe_ai_observation(item, mask, item_key)
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [ExecutionService._safe_ai_observation(item, mask, key) for item in value]
        if isinstance(value, str):
            return _safe_url(value) if key in {"url", "href", "action"} else mask(value)
        return value

    def _configured_secrets(self) -> list[str]:
        secrets = [self._settings.test_credential_username or ""]
        if self._settings.test_credential_password is not None:
            secrets.append(self._settings.test_credential_password.get_secret_value())
        return secrets

    @staticmethod
    def _finish(
        result: TestExecutionResult,
        status: TestExecutionStatus,
        reason: str,
        page_state: dict[str, Any],
        started_clock: float,
        console_errors: list[dict[str, str]],
        network_errors: list[dict[str, str]],
    ) -> None:
        result.status = status
        result.failure_reason = reason if status in {TestExecutionStatus.FAILED, TestExecutionStatus.BLOCKED} else None
        result.actual_result = str(page_state.get("visible_text", ""))[:12000]
        result.duration = round(time.perf_counter() - started_clock, 3)
        result.completed_at = datetime.now(UTC)
        result.console_errors = console_errors
        result.network_errors = network_errors
