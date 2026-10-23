"""Stage 1 adapter contracts. No university-specific extraction is implemented."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    original_url: str
    captured_at: str
    sha256: str
    local_path: str


@dataclass(frozen=True)
class ExtractionResult:
    source_id: str
    status: str
    records: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    adapter_version: str


class Adapter(Protocol):
    """Implement against saved snapshots; failures must not fabricate rows."""

    def extract(self, snapshot: SourceSnapshot) -> ExtractionResult: ...
