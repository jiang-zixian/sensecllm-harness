from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = Path(os.getenv(name, str(default))).expanduser()
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


@dataclass(frozen=True)
class HarnessSettings:
    project_root: Path = PROJECT_ROOT
    runs_dir: Path = field(
        default_factory=lambda: _env_path("SENSECLLM_RUNS_DIR", PROJECT_ROOT / "runs")
    )
    memory_db: Path = field(
        default_factory=lambda: _env_path(
            "SENSECLLM_MEMORY_DB", PROJECT_ROOT / "runs" / "memory.sqlite3"
        )
    )
    default_model: str = os.getenv("SENSECLLM_MODEL", "deepseek-v3.2")
    agent_timeout_seconds: int = int(os.getenv("SENSECLLM_AGENT_TIMEOUT_SECONDS", "900"))
    run_timeout_seconds: int = int(os.getenv("SENSECLLM_RUN_TIMEOUT_SECONDS", "3600"))
    max_agent_attempts: int = int(os.getenv("SENSECLLM_MAX_AGENT_ATTEMPTS", "2"))
    max_total_agent_attempts: int = int(os.getenv("SENSECLLM_MAX_TOTAL_AGENT_ATTEMPTS", "24"))
    max_model_tokens: int = int(os.getenv("SENSECLLM_MAX_MODEL_TOKENS", "500000"))
    max_estimated_cost: float = float(os.getenv("SENSECLLM_MAX_ESTIMATED_COST", "0"))
    retry_backoff_seconds: float = float(os.getenv("SENSECLLM_RETRY_BACKOFF_SECONDS", "1.0"))
    critic_enabled: bool = os.getenv("SENSECLLM_CRITIC_ENABLED", "true").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    critic_model: str = os.getenv("SENSECLLM_CRITIC_MODEL", "deepseek-v3.2")
    orchestrator: str = os.getenv("SENSECLLM_ORCHESTRATOR", "langgraph")

    def ensure_directories(self) -> None:
        if self.orchestrator not in {"langgraph", "sequential"}:
            raise ValueError("SENSECLLM_ORCHESTRATOR must be langgraph or sequential")
        self.runs_dir.expanduser().resolve().mkdir(parents=True, exist_ok=True)
        self.memory_db.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
