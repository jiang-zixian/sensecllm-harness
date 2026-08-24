from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sensecllm.harness.checkpoint import CheckpointStore


def collect(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        state = CheckpointStore().load(path)
        usage = state.metadata.get("usage", {})
        config = state.metadata.get("experiment_config", {})
        graph_path = state.data_dir / "step2_mechanism_paths.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else {}
        rows.append(
            {
                "run_id": state.run_id,
                "status": state.status.value,
                "model": state.model,
                **config,
                "execution_seconds": usage.get("execution_seconds", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "model_calls": usage.get("model_calls", 0),
                "agent_attempts": usage.get("total_agent_attempts", 0),
                "accepted_paths": len(graph.get("accepted_paths", [])),
                "unresolved_paths": len(graph.get("unresolved_paths", [])),
                "rejected_paths": len(graph.get("rejected_paths", [])),
            }
        )
    return rows


def svg(rows: list[dict[str, Any]]) -> str:
    width, height = 900, 420
    maximum = max((float(row["total_tokens"]) for row in rows), default=1.0) or 1.0
    bars = []
    for index, row in enumerate(rows):
        x = 85 + index * max(120, 700 // max(1, len(rows)))
        bar_height = 260 * float(row["total_tokens"]) / maximum
        y = 330 - bar_height
        label = f'{row.get("agent_profile", "full")}/{"rag" if row.get("rag_enabled", True) else "no-rag"}'
        bars.append(f'<rect x="{x}" y="{y:.1f}" width="80" height="{bar_height:.1f}" rx="8" fill="#56d6c9"/>')
        bars.append(f'<text x="{x}" y="355" fill="#dce9f5" font-size="12">{label}</text>')
        bars.append(f'<text x="{x}" y="{max(20, y-8):.1f}" fill="#dce9f5" font-size="12">{row["total_tokens"]}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#08111d"/><text x="40" y="38" fill="#e9f2fa" font-size="22">Real-run token comparison</text>
<line x1="55" y1="330" x2="850" y2="330" stroke="#42617f"/>{''.join(bars)}</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoints", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("evals/results/ablations.json"))
    args = parser.parse_args()
    rows = collect(args.checkpoints)
    payload = {
        "scope": "operational comparison on one synthetic document; no accuracy claim",
        "runs": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.with_suffix(".svg").write_text(svg(rows), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
