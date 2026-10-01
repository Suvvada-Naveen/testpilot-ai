from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator



class FailureClassification(str, Enum):
    APPLICATION_DEFECT = "APPLICATION_DEFECT"
    TEST_EXECUTION_ERROR = "TEST_EXECUTION_ERROR"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    TEST_DATA_ERROR = "TEST_DATA_ERROR"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_A_DEFECT = "NOT_A_DEFECT"


class AnalysisConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    execution_id: str
    classification: FailureClassification
    confidence: AnalysisConfidence
    summary: str = Field(min_length=1, max_length=1200)
    expected_behavior: str = Field(min_length=1, max_length=1200)
    actual_behavior: str = Field(min_length=1, max_length=1200)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    possible_causes: list[str] = Field(default_factory=list, max_length=10)
    recommended_next_step: str = Field(min_length=1, max_length=1200)
    needs_review: bool

    @model_validator(mode="after")
    def ambiguous_requires_review(self) -> "FailureAnalysis":
        if self.classification == FailureClassification.AMBIGUOUS and not self.needs_review:
            raise ValueError("Ambiguous analyses must require review")
        return self


