from collections.abc import Mapping
from typing import Any

from app.ai.ai_client import AIClient
from app.agent.prompts import ACTION_PLANNER_PROMPT, action_user_message
from app.schemas.browser_action import BrowserAction, BrowserToolName
from app.schemas.test_plan import TestCase

AVAILABLE_BROWSER_TOOLS = list(BrowserToolName)


class ActionPlanner:
    def __init__(self, ai_client: AIClient) -> None:
        self._ai_client = ai_client

    async def next_action(
        self,
        test_case: TestCase,
        page_state: Mapping[str, Any],
        previous_actions: list[Mapping[str, Any]],
        action_results: list[Mapping[str, Any]],
    ) -> BrowserAction:
        return await self._ai_client.generate_structured_response(
            ACTION_PLANNER_PROMPT,
            action_user_message(
                test_case.model_dump(mode="json"),
                page_state,
                AVAILABLE_BROWSER_TOOLS,
                previous_actions,
                action_results,
            ),
            BrowserAction,
        )
