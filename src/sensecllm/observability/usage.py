from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def record_model_usage(
    path: Path | str | None,
    *,
    provider: str,
    model: str,
    usage: dict[str, Any] | None,
    operation: str = "chat",
) -> None:
    if not path:
        return
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    input_rate = float(os.getenv("SENSECLLM_INPUT_COST_PER_MTOK", "0") or 0)
    output_rate = float(os.getenv("SENSECLLM_OUTPUT_COST_PER_MTOK", "0") or 0)
    estimated_cost = (
        prompt_tokens * input_rate / 1_000_000
        + completion_tokens * output_rate / 1_000_000
    )
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "operation": operation,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": round(estimated_cost, 8) if input_rate or output_rate else None,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def summarize_usage(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    costs = [float(item["estimated_cost"]) for item in records if item.get("estimated_cost")]
    by_model: dict[str, dict[str, int]] = {}
    for item in records:
        model = str(item.get("model") or "unknown")
        summary = by_model.setdefault(model, {"calls": 0, "tokens": 0})
        summary["calls"] += 1
        summary["tokens"] += int(item.get("total_tokens") or 0)
    return {
        "model_calls": len(records),
        "prompt_tokens": sum(int(item.get("prompt_tokens") or 0) for item in records),
        "completion_tokens": sum(
            int(item.get("completion_tokens") or 0) for item in records
        ),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in records),
        "estimated_cost": round(sum(costs), 8) if costs else None,
        "by_model": by_model,
        "pricing_configured": bool(
            os.getenv("SENSECLLM_INPUT_COST_PER_MTOK")
            or os.getenv("SENSECLLM_OUTPUT_COST_PER_MTOK")
        ),
    }
