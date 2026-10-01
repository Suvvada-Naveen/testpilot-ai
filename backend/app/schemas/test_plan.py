from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TestCaseType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    VALIDATION = "validation"
    BOUNDARY = "boundary"
    NAVIGATION = "navigation"
    UI = "ui"
    SECURITY = "security"
    OTHER = "other"


class TestPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^TC\d{3,}$", max_length=12)
    title: str = Field(min_length=1, max_length=160)
    type: TestCaseType
    priority: TestPriority
    description: str = Field(min_length=1, max_length=1200)
    preconditions: list[str] = Field(max_length=20)
    steps: list[str] = Field(min_length=1, max_length=30)
    expected_result: str = Field(min_length=1, max_length=1200)
    target_elements: list[str] = Field(min_length=1, max_length=30)
    requires_credentials: bool = False


class TestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=500)
    test_cases: list[TestCase] = Field(max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def test_case_ids_are_unique(self) -> "TestPlan":
        ids = [test_case.id for test_case in self.test_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Test case IDs must be unique")
        return self