from pydantic import BaseModel

from app.schemas.bug_report import BugReport
from app.schemas.evidence import Evidence
from app.schemas.failure_analysis import FailureAnalysis


class FailureAnalysisResponse(BaseModel):
    analysis: FailureAnalysis
    bug_report: BugReport
    evidence: list[Evidence]