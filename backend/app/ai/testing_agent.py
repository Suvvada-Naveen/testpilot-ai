import json
import logging
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.ai.ai_client import AIClient, InvalidAIResponseError
from app.core.config import Settings
from app.schemas.test_plan import TestPlan

logger = logging.getLogger(__name__)
ELEMENT_COLLECTIONS = (
    "headings", "buttons", "inputs", "links", "forms", "checkboxes", "radio_buttons", "selects",
)
ELEMENT_FIELDS = {
    "buttons": ("text", "aria_label", "disabled"),
    "inputs": ("type", "name", "id", "placeholder", "required", "aria_label"),
    "links": ("text", "href"),
    "forms": ("name", "action", "method"),
    "checkboxes": ("name", "id", "checked", "required"),
    "radio_buttons": ("name", "value", "checked"),
    "selects": ("name", "id", "options"),
}


def _clip_strings(value: Any, max_length: int = 500) -> Any:
    if isinstance(value, str):
        return value[:max_length]
    if isinstance(value, list):
        return [_clip_strings(item, max_length) for item in value]
    if isinstance(value, dict):
        return {key: _clip_strings(item, max_length) for key, item in value.items()}
    return value


def _safe_page_url(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return value[:500]


def _sanitize_element(collection: str, item: Any, max_options: int = 0) -> Any:
    if collection == "headings":
        return _clip_strings(item)
    if not isinstance(item, Mapping):
        return None
    sanitized = {key: item[key] for key in ELEMENT_FIELDS[collection] if key in item}
    if collection == "links" and "href" in sanitized:
        sanitized["href"] = _safe_page_url(sanitized["href"])
    if collection == "forms" and "action" in sanitized:
        sanitized["action"] = _safe_page_url(sanitized["action"])
    if collection == "selects" and isinstance(sanitized.get("options"), list):
        sanitized["options"] = [
            {key: option[key] for key in ("text", "value") if key in option}
            for option in sanitized["options"][:max_options]
            if isinstance(option, Mapping)
        ]
    return _clip_strings(sanitized)


def prepare_inspection_for_ai(inspection: Mapping[str, Any], settings: Settings) -> dict[str, Any]:
    page = inspection.get("page", {})
    page = page if isinstance(page, Mapping) else {}
    raw_elements = inspection.get("elements", {})
    raw_elements = raw_elements if isinstance(raw_elements, Mapping) else {}
    remaining = max(0, settings.max_ai_elements)
    elements: dict[str, list[Any]] = {}

    for collection in ELEMENT_COLLECTIONS:
        raw_items = raw_elements.get(collection, [])
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
            raw_items = []
        link_limit = settings.max_ai_links if collection == "links" else remaining
        selected: list[Any] = []
        seen: set[str] = set()
        for item in raw_items:
            if remaining <= 0 or len(selected) >= link_limit:
                break
            option_budget = max(0, remaining - 1) if collection == "selects" else 0
            sanitized = _sanitize_element(collection, item, option_budget)
            if sanitized is None:
                continue
            marker = json.dumps(sanitized, sort_keys=True, ensure_ascii=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            nested_count = len(sanitized.get("options", [])) if collection == "selects" else 0
            selected.append(sanitized)
            remaining -= 1 + nested_count
        elements[collection] = selected

    visible_text = inspection.get("visible_text", "")
    if not isinstance(visible_text, str):
        visible_text = ""
    visible_text = "\n".join(line.strip() for line in visible_text.splitlines() if line.strip())
    repeated_element_text: set[str] = set()
    for heading in elements["headings"]:
        if isinstance(heading, str):
            repeated_element_text.add(heading.casefold())
    for collection in ("buttons", "links"):
        for item in elements[collection]:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                repeated_element_text.add(item["text"].casefold())
    visible_text = "\n".join(
        line for line in visible_text.splitlines() if line.casefold() not in repeated_element_text
    )[:max(0, settings.max_ai_page_text)]

    return {
        "url": _safe_page_url(str(page.get("final_url") or page.get("requested_url") or ""))[:500],
        "title": str(page.get("title") or "")[:500],
        "visible_text": visible_text,
        "elements": elements,
    }


def _normalized_element(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _allowed_target_elements(inspection: Mapping[str, Any]) -> set[str]:
    allowed: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            allowed.add(_normalized_element(value))

    elements = inspection.get("elements", {})
    if not isinstance(elements, Mapping):
        return allowed

    for heading in elements.get("headings", []):
        add(heading)
    for collection, suffix in (("buttons", "button"), ("links", "link")):
        for element in elements.get(collection, []):
            if not isinstance(element, Mapping):
                continue
            for key in ("text", "aria_label", "href"):
                value = element.get(key)
                add(value)
                if key == "text" and value:
                    add(f"{value} {suffix}")
    for collection, suffix in (
        ("inputs", "field"), ("checkboxes", "checkbox"), ("radio_buttons", "radio button"),
        ("selects", "select"),
    ):
        for element in elements.get(collection, []):
            if not isinstance(element, Mapping):
                continue
            for key in ("name", "id", "placeholder", "aria_label", "value"):
                value = element.get(key)
                add(value)
                if key in {"name", "id"} and value:
                    add(f"{value} {suffix}")
                    if collection == "inputs":
                        add(f"{value} input")
    for form in elements.get("forms", []):
        if isinstance(form, Mapping):
            add(form.get("name"))
            add(form.get("action"))
    for select in elements.get("selects", []):
        if isinstance(select, Mapping):
            for option in select.get("options", []):
                if isinstance(option, Mapping):
                    add(option.get("text"))
                    add(option.get("value"))
    return allowed


class TestingAgent:
    def __init__(self, ai_client: AIClient, settings: Settings) -> None:
        self._ai_client = ai_client
        self._settings = settings

    async def generate_test_plan(
        self,
        session_id: str,
        instruction: str,
        inspection: Mapping[str, Any],
    ) -> TestPlan:
        logger.info("AI test plan generation started session_id=%s", session_id)
        prepared_inspection = prepare_inspection_for_ai(inspection, self._settings)
        try:
            plan = await self._ai_client.generate_test_plan(instruction, prepared_inspection)
        except Exception as error:
            logger.warning("AI test plan generation failed session_id=%s error_type=%s", session_id, type(error).__name__)
            raise
        if len(plan.test_cases) > self._settings.max_ai_test_cases:
            raise InvalidAIResponseError("The AI returned an invalid test plan. Please try again.")

        allowed_elements = _allowed_target_elements(prepared_inspection)
        for test_case in plan.test_cases:
            invalid_targets = [
                target for target in test_case.target_elements
                if _normalized_element(target) not in allowed_elements
            ]
            if invalid_targets:
                logger.warning("AI returned untraceable target elements session_id=%s", session_id)
                raise InvalidAIResponseError("The AI returned an invalid test plan. Please try again.")

        if any(test_case.requires_credentials for test_case in plan.test_cases) and not any(
            "credential" in warning.casefold() for warning in plan.warnings
        ):
            warnings = [*plan.warnings, "Some scenarios require credentials; provide them securely during a later execution phase, not in this prompt."]
            plan = plan.model_copy(update={"warnings": warnings})

        logger.info("AI test plan generation completed session_id=%s test_count=%s", session_id, len(plan.test_cases))
        return plan
