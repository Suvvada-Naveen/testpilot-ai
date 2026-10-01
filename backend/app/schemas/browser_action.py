from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrowserToolName(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    SCROLL = "scroll"
    WAIT = "wait"
    READ_PAGE = "read_page"
    TAKE_SCREENSHOT = "take_screenshot"


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: BrowserToolName
    target: str | None = Field(default=None, max_length=2048)
    value: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_action_arguments(self) -> "BrowserAction":
        target_actions = {
            BrowserToolName.NAVIGATE, BrowserToolName.CLICK, BrowserToolName.FILL,
            BrowserToolName.SELECT, BrowserToolName.CHECK, BrowserToolName.UNCHECK,
            BrowserToolName.PRESS,
        }
        value_actions = {
            BrowserToolName.FILL, BrowserToolName.SELECT, BrowserToolName.PRESS,
            BrowserToolName.SCROLL, BrowserToolName.WAIT,
        }
        if self.action in target_actions and not self.target:
            raise ValueError("This action requires a target")
        if self.action not in target_actions and self.target is not None:
            raise ValueError("This action does not accept a target")
        if self.action in value_actions and not self.value:
            raise ValueError("This action requires a value")
        if self.action not in value_actions and self.value is not None:
            raise ValueError("This action does not accept a value")
        if self.action == BrowserToolName.SCROLL and self.value not in {"up", "down"}:
            raise ValueError("Scroll value must be 'up' or 'down'")
        if self.action == BrowserToolName.WAIT:
            try:
                wait_ms = int(self.value or "")
            except ValueError as error:
                raise ValueError("Wait value must be milliseconds") from error
            if not 0 <= wait_ms <= 10000:
                raise ValueError("Wait value must be between 0 and 10000 milliseconds")
        return self


class EvaluationStatus(str, Enum):
    CONTINUE = "CONTINUE"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class ProgressEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    finished: bool
    status: EvaluationStatus
    reason: str = Field(min_length=1, max_length=1200)
    evidence: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_finished_status(self) -> "ProgressEvaluation":
        if self.finished == (self.status == EvaluationStatus.CONTINUE):
            raise ValueError("CONTINUE must be unfinished; terminal statuses must be finished")
        return self