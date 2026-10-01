import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SECRET_ASSIGNMENT = re.compile(r"(?i)(password|passwd|token|authorization|api[_ -]?key|secret|cookie)(\s*[:=]\s*)((?:Bearer\s+)?[^\s,;]+)")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_API_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_CARD_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_SENSITIVE_KEY = re.compile(r"(?i)(password|passwd|token|authorization|api[_ -]?key|secret|cookie|card[_ -]?(number|cvc|cvv))")


def safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def redact_sensitive_text(value: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "********")
    value = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    value = _BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    value = _API_KEY.sub("[REDACTED_API_KEY]", value)
    return _CARD_NUMBER.sub("[REDACTED_NUMBER]", value)


def sanitize_sensitive_data(value: Any, secrets: list[str] | tuple[str, ...] = (), key: str = "") -> Any:
    if isinstance(value, dict):
        return {item_key: sanitize_sensitive_data(item, secrets, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_sensitive_data(item, secrets, key) for item in value[:200]]
    if isinstance(value, str):
        if _SENSITIVE_KEY.search(key):
            return "[REDACTED]"
        if key in {"url", "href", "action", "requested_url", "final_url"}:
            value = safe_url(value)
        return redact_sensitive_text(value[:12000], secrets)
    return value
