from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TestMode(str, Enum):
    EXPLORE = "EXPLORE"
    TEST = "TEST"
    FULL_TEST = "FULL_TEST"


class TestStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class TestSession:
    id: str
    url: str
    instruction: str
    mode: TestMode
    status: TestStatus
    created_at: datetime
    updated_at: datetime