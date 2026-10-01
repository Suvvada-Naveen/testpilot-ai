from threading import RLock

from app.schemas.bug_report import BugReport


class BugReportRepository:
    def __init__(self) -> None:
        self._reports: dict[str, BugReport] = {}
        self._execution_ids: dict[str, str] = {}
        self._session_ids: dict[str, list[str]] = {}
        self._lock = RLock()

    def create(self, session_id: str, report: BugReport) -> BugReport:
        with self._lock:
            previous_id = self._execution_ids.get(report.execution_id)
            if previous_id is not None:
                self._reports.pop(previous_id, None)
                ids = self._session_ids.get(session_id, [])
                self._session_ids[session_id] = [item for item in ids if item != previous_id]
            stored = report.model_copy(deep=True)
            self._reports[stored.id] = stored
            self._execution_ids[stored.execution_id] = stored.id
            self._session_ids.setdefault(session_id, []).append(stored.id)
            return stored.model_copy(deep=True)

    def get_by_execution_id(self, execution_id: str) -> BugReport | None:
        with self._lock:
            report_id = self._execution_ids.get(execution_id)
            report = self._reports.get(report_id) if report_id else None
            return report.model_copy(deep=True) if report is not None else None

    def list_by_session_id(self, session_id: str) -> list[BugReport]:
        with self._lock:
            return [
                self._reports[item].model_copy(deep=True)
                for item in self._session_ids.get(session_id, [])
                if item in self._reports
            ]

    def delete_by_session_id(self, session_id: str) -> None:
        with self._lock:
            for report_id in self._session_ids.pop(session_id, []):
                report = self._reports.pop(report_id, None)
                if report is not None:
                    self._execution_ids.pop(report.execution_id, None)

    def delete_by_execution_id(self, session_id: str, execution_id: str) -> bool:
        with self._lock:
            report_id = self._execution_ids.pop(execution_id, None)
            if report_id is None:
                return False
            self._reports.pop(report_id, None)
            self._session_ids[session_id] = [item for item in self._session_ids.get(session_id, []) if item != report_id]
            return True
