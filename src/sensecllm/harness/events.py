from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .state import utc_now


@dataclass(frozen=True)
class HarnessEvent:
    event: str
    run_id: str
    stage: str | None = None
    timestamp: str = field(default_factory=utc_now)
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self, event_file: Path | None = None) -> None:
        self.event_file = event_file
        self._subscribers: list[Callable[[HarnessEvent], None]] = []

    def subscribe(self, callback: Callable[[HarnessEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, event: HarnessEvent) -> None:
        if self.event_file is not None:
            self.event_file.parent.mkdir(parents=True, exist_ok=True)
            with self.event_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        for callback in tuple(self._subscribers):
            callback(event)
