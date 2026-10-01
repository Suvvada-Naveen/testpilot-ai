from threading import RLock

from app.schemas.evidence import Evidence, FailureEvidenceBundle


class EvidenceRepository:
    """In-memory evidence artifacts, replaceable with durable object storage later."""

    def __init__(self) -> None:
        self._bundles: dict[str, FailureEvidenceBundle] = {}
        self._lock = RLock()

    def save_bundle(self, bundle: FailureEvidenceBundle) -> FailureEvidenceBundle:
        with self._lock:
            stored = bundle.model_copy(deep=True)
            self._bundles[stored.execution_id] = stored
            return stored.model_copy(deep=True)

    def get_by_execution_id(self, execution_id: str) -> FailureEvidenceBundle | None:
        with self._lock:
            bundle = self._bundles.get(execution_id)
            return bundle.model_copy(deep=True) if bundle is not None else None

    def list_by_execution_ids(self, execution_ids: list[str]) -> list[Evidence]:
        with self._lock:
            return [
                item.model_copy(deep=True)
                for execution_id in execution_ids
                for bundle in [self._bundles.get(execution_id)]
                if bundle is not None
                for item in bundle.evidence
            ]

    def delete_by_execution_id(self, execution_id: str) -> bool:
        with self._lock:
            return self._bundles.pop(execution_id, None) is not None
