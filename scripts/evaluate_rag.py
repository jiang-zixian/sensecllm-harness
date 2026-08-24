from __future__ import annotations

import argparse
import json
from pathlib import Path

from sensecllm.evaluation import evaluate_rag
from sensor_rag.pipeline import SensorRAG


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("judgments", type=Path)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("evals/results/rag.json"))
    args = parser.parse_args()
    result = evaluate_rag(SensorRAG(), args.judgments, args.k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
