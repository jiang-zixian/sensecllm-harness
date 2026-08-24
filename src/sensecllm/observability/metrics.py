from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from sensecllm.harness.checkpoint import CheckpointStore


def collect_metrics(runs_dir: Path) -> dict[str, Any]:
    states = []
    for checkpoint in runs_dir.expanduser().resolve().glob("*/checkpoint.json"):
        try:
            states.append(CheckpointStore().load(checkpoint))
        except (OSError, ValueError):
            continue
    statuses = Counter(state.status.value for state in states)
    total_attempts = sum(
        int(state.metadata.get("usage", {}).get("total_agent_attempts", 0))
        for state in states
    )
    total_retries = sum(
        int(state.metadata.get("usage", {}).get("retry_count", 0)) for state in states
    )
    total_tokens = sum(
        int(state.metadata.get("usage", {}).get("total_tokens", 0)) for state in states
    )
    return {
        "runs_total": len(states),
        "runs_by_status": dict(statuses),
        "agent_attempts_total": total_attempts,
        "agent_retries_total": total_retries,
        "model_tokens_total": total_tokens,
    }


def prometheus_metrics(metrics: dict[str, Any]) -> str:
    lines = [
        "# TYPE sensecllm_runs_total counter",
        f"sensecllm_runs_total {metrics['runs_total']}",
    ]
    for status, count in sorted(metrics["runs_by_status"].items()):
        lines.append(f'sensecllm_runs_status_total{{status="{status}"}} {count}')
    lines.extend(
        [
            "# TYPE sensecllm_agent_attempts_total counter",
            f"sensecllm_agent_attempts_total {metrics['agent_attempts_total']}",
            "# TYPE sensecllm_agent_retries_total counter",
            f"sensecllm_agent_retries_total {metrics['agent_retries_total']}",
            "# TYPE sensecllm_model_tokens_total counter",
            f"sensecllm_model_tokens_total {metrics['model_tokens_total']}",
        ]
    )
    return "\n".join(lines) + "\n"
