from collections.abc import Mapping
from typing import Any

from app.ai.ai_client import AIClient
from app.agent.prompts import RESULT_EVALUATOR_PROMPT, evaluation_user_message
from app.schemas.browser_action import ProgressEvaluation
from app.schemas.test_plan import TestCase


class ResultEvaluator:
    def __init__(self, ai_client: AIClient) -> None:
        self._ai_client = ai_client

    async def evaluate(
        self,
        test_case: TestCase,
        page_state: Mapping[str, Any],
        action_history: list[Mapping[str, Any]],
        console_errors: list[Mapping[str, Any]],
        network_errors: list[Mapping[str, Any]],
    ) -> ProgressEvaluation:
        return await self._ai_client.generate_structured_response(
            RESULT_EVALUATOR_PROMPT,
            evaluation_user_message(
                test_case.expected_result,
                page_state,
                action_history,
                console_errors,
                network_errors,
            ),
            ProgressEvaluation,
        )
