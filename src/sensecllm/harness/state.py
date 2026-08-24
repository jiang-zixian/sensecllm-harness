from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StageRecord:
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    attempts: int = 0
    failure_class: str | None = None
    output_preview: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageRecord:
        payload = dict(data)
        payload["status"] = StageStatus(payload.get("status", StageStatus.PENDING))
        return cls(**payload)


@dataclass
class RunState:
    run_id: str
    input_path: str
    run_dir: str
    report_path: str
    model: str
    status: RunStatus = RunStatus.PENDING
    current_stage: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    stages: dict[str, StageRecord] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def data_dir(self) -> Path:
        report = Path(self.report_path)
        return report.parent / "temp_data" / report.stem

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        for record in payload["stages"].values():
            record["status"] = record["status"].value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        payload = dict(data)
        payload["status"] = RunStatus(payload.get("status", RunStatus.PENDING))
        payload["stages"] = {
            name: StageRecord.from_dict(record)
            for name, record in payload.get("stages", {}).items()
        }
        return cls(**payload)
