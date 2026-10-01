from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.browser_action import BrowserToolName


class TestExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ActionExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ActionExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    step: int = Field(ge=1)
    action: BrowserToolName
    target: str | None = Field(default=None, max_length=500)
    status: ActionExecutionStatus
    duration_ms: int = Field(ge=0)
    error: str | None = Field(default=None, max_length=1000)


class TestExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    session_id: str
    test_case_id: str
    status: TestExecutionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration: float = Field(ge=0)
    actions: list[ActionExecution] = Field(default_factory=list)
    expected_result: str
    actual_result: str = ""
    failure_reason: str | None = None
    screenshot_id: str | None = None
    console_errors: list[dict[str, str]] = Field(default_factory=list)
    network_errors: list[dict[str, str]] = Field(default_factory=list)


class ExecuteTestsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_case_ids: list[str] | None = Field(default=None, max_length=30)
    confirm_destructive: bool = False

    @field_validator("test_case_ids")
    @classmethod
    def unique_test_case_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (not value or len(value) != len(set(value))):
            raise ValueError("Select at least one unique test case")
        return value


class ExecuteTestCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_destructive: bool = False


class ExecutionBatchResponse(BaseModel):
    session_id: str
    status: str
    total: int
    execution_ids: list[str]
    executions: list[TestExecutionResult]