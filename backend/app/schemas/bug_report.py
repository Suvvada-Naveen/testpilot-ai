from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.failure_analysis import FailureClassification


class BugSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class BugPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class BugReportStatus(str, Enum):
    OPEN = "OPEN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DRAFT = "DRAFT"


class BugReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1600)
    module: str = Field(min_length=1, max_length=200)
    severity: BugSeverity
    priority: BugPriority
    possible_cause: str = Field(min_length=1, max_length=1200)


class BugReport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    execution_id: str
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1600)
    module: str = Field(min_length=1, max_length=200)
    severity: BugSeverity
    priority: BugPriority
    environment: str = Field(max_length=500)
    url: str = Field(max_length=1000)
    preconditions: list[str] = Field(default_factory=list, max_length=20)
    steps_to_reproduce: list[str] = Field(min_length=1, max_length=30)
    expected_result: str = Field(min_length=1, max_length=1200)
    actual_result: str = Field(min_length=1, max_length=1200)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    observed_behavior: str = Field(min_length=1, max_length=1200)
    possible_cause: str = Field(min_length=1, max_length=1200)
    classification: FailureClassification
    status: BugReportStatus
    created_at: datetime
