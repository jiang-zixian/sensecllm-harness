from __future__ import annotations

import argparse
from pathlib import Path

from sensecllm.legacy import LegacyPipelineAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="isolated SenseCLLM legacy stage worker")
    parser.add_argument(
        "stage", choices=["document", "mechanism", "vulnerability", "experiment", "defense"]
    )
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--model", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = LegacyPipelineAdapter(args.project_root, args.input, args.report)
    adapter.run_stage(args.stage, args.model)
    print(f"[HarnessWorker] stage={args.stage} status=completed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
