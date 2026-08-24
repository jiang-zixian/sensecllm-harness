from __future__ import annotations

import json
from pathlib import Path

from .state import RunState, utc_now


class CheckpointStore:
    def checkpoint_path(self, state: RunState) -> Path:
        return Path(state.run_dir) / "checkpoint.json"

    def save(self, state: RunState) -> Path:
        state.updated_at = utc_now()
        path = self.checkpoint_path(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def load(self, path: Path) -> RunState:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RunState.from_dict(payload)
