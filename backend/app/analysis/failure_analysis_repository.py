from threading import RLock

from app.schemas.failure_analysis import FailureAnalysis


class FailureAnalysisRepository:
    def __init__(self) -> None:
        self._analyses: dict[str, FailureAnalysis] = {}
        self._lock = RLock()

    def create(self, analysis: FailureAnalysis) -> FailureAnalysis:
        with self._lock:
            self._analyses[analysis.execution_id] = analysis.model_copy(deep=True)
            return analysis.model_copy(deep=True)

    def get_by_execution_id(self, execution_id: str) -> FailureAnalysis | None:
        with self._lock:
            analysis = self._analyses.get(execution_id)
            return analysis.model_copy(deep=True) if analysis is not None else None

    def delete_by_execution_id(self, execution_id: str) -> bool:
        with self._lock:
            return self._analyses.pop(execution_id, None) is not None
