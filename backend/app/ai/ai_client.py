import logging
from collections.abc import Mapping
from typing import Any, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, AuthenticationError, OpenAIError, RateLimitError
from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.test_plan import TestPlan
from app.ai.prompts import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class AIServiceError(RuntimeError):
    pass


class MissingAPIKeyError(AIServiceError):
    pass


class InvalidAIResponseError(AIServiceError):
    pass


class AIProviderError(AIServiceError):
    pass


class AIClient:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client
        api_key = settings.openai_api_key
        if self._client is None and api_key is not None and api_key.get_secret_value().strip():
            self._client = AsyncOpenAI(
                api_key=api_key.get_secret_value(),
                timeout=settings.openai_timeout_seconds,
            )

    async def generate_test_plan(self, instruction: str, inspection: Mapping[str, Any]) -> TestPlan:
        return await self.generate_structured_response(
            SYSTEM_PROMPT,
            build_user_message(instruction, inspection),
            TestPlan,
        )

    async def generate_structured_response(
        self,
        system_prompt: str,
        user_message: str,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        if self._client is None:
            raise MissingAPIKeyError("The AI service is not configured. Add OPENAI_API_KEY to the backend environment.")

        try:
            response = await self._client.responses.parse(
                model=self._settings.openai_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                text_format=response_model,
            )
        except AuthenticationError as error:
            logger.warning("OpenAI authentication failed")
            raise AIProviderError("AI test generation is temporarily unavailable. Please try again.") from error
        except RateLimitError as error:
            logger.warning("OpenAI rate limit reached")
            raise AIProviderError("AI test generation is temporarily unavailable. Please try again.") from error
        except (APITimeoutError, APIConnectionError, APIStatusError, OpenAIError) as error:
            logger.warning("OpenAI request failed (%s)", type(error).__name__)
            raise AIProviderError("AI test generation is temporarily unavailable. Please try again.") from error
        except Exception as error:
            logger.warning("OpenAI response could not be parsed (%s)", type(error).__name__)
            raise InvalidAIResponseError("The AI returned an invalid test plan. Please try again.") from error

        plan = getattr(response, "output_parsed", None)
        if not isinstance(plan, response_model):
            logger.warning("OpenAI returned no valid structured test plan")
            raise InvalidAIResponseError("The AI returned an invalid structured response. Please try again.")
        return plan