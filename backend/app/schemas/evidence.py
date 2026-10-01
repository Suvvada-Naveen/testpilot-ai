from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(str, Enum):
    SCREENSHOT = "SCREENSHOT"
    PAGE_STATE = "PAGE_STATE"
    ACTION_LOG = "ACTION_LOG"
    CONSOLE_ERROR = "CONSOLE_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    PAGE_TEXT = "PAGE_TEXT"
    EXECUTION_LOG = "EXECUTION_LOG"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    execution_id: str
    type: EvidenceType
    description: str = Field(min_length=1, max_length=1000)
    created_at: datetime
    reference: str = Field(min_length=1, max_length=1000)


class FailureEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    evidence: list[Evidence] = Field(max_length=200)
    context: dict[str, object]
