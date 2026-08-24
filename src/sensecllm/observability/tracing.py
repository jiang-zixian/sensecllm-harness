from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    name: str
    started_at: str
    ended_at: str
    status: str
    duration_ms: float
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class TraceRecorder:
    def __init__(self, path: Path, trace_id: str) -> None:
        self.path = path
        self.trace_id = trace_id

    def record(
        self,
        *,
        name: str,
        started_at: str,
        ended_at: str,
        status: str,
        attributes: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> TraceSpan:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
        span = TraceSpan(
            trace_id=self.trace_id,
            span_id=uuid.uuid4().hex,
            name=name,
            started_at=started_at,
            ended_at=ended_at,
            status=status,
            duration_ms=round((end - start).total_seconds() * 1000, 3),
            attributes=attributes or {},
            error=error,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(span), ensure_ascii=False) + "\n")
        return span

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
