from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_OTEL_TRACER: Any = None
_OTEL_CONFIGURED = False


def _otel_tracer() -> Any:
    global _OTEL_CONFIGURED, _OTEL_TRACER
    if _OTEL_CONFIGURED:
        return _OTEL_TRACER
    _OTEL_CONFIGURED = True
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": "sensecllm-harness"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _OTEL_TRACER = trace.get_tracer("sensecllm.harness")
    return _OTEL_TRACER


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
        tracer = _otel_tracer()
        if tracer is not None:
            exported = tracer.start_span(
                name,
                start_time=int(start.timestamp() * 1_000_000_000),
                attributes={key: value for key, value in span.attributes.items() if value is not None},
            )
            if error:
                exported.set_attribute("error.message", error)
            exported.set_attribute("sensecllm.status", status)
            exported.end(end_time=int(end.timestamp() * 1_000_000_000))
        return span

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
