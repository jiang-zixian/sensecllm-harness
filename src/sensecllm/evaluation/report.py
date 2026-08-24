from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Any


def bootstrap_ci(values: list[float], samples: int = 2000, seed: int = 42) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "lower_95": 0.0, "upper_95": 0.0}
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(samples))
    return {
        "mean": round(statistics.fmean(values), 6),
        "lower_95": round(means[int(samples * 0.025)], 6),
        "upper_95": round(means[min(samples - 1, int(samples * 0.975))], 6),
    }


def generate_report(result_paths: list[Path], output: Path) -> dict[str, Any]:
    results = [json.loads(path.read_text(encoding="utf-8")) for path in result_paths]
    keys = [
        "sensor_type_exact_match",
        "extraction_field_f1",
        "evidence_support_precision",
        "unsupported_claim_rate",
        "experiment_constraint_pass_rate",
    ]
    summary: dict[str, Any] = {"case_count": len(results), "metrics": {}}
    for key in keys:
        values = [float(item["metrics"][key]) for item in results if key in item["metrics"]]
        summary["metrics"][key] = bootstrap_ci(values)
    for key in ("mechanisms", "vulnerabilities"):
        values = [float(item["metrics"][key]["f1"]) for item in results]
        summary["metrics"][f"{key}_f1"] = bootstrap_ci(values)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
