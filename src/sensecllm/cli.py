from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sensecllm.config import HarnessSettings
from sensecllm.evaluation import BenchmarkCase, evaluate_run
from sensecllm.harness.checkpoint import CheckpointStore
from sensecllm.harness.runner import HarnessRunner
from sensecllm.memory.episodic import EpisodicMemoryStore


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sensecllm")
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="run a sensor security analysis")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--model", default=None)
    analyze.add_argument(
        "--profile", choices=["full", "single_agent", "no_memory", "no_critic"], default="full"
    )

    resume = commands.add_parser("resume", help="resume a failed or interrupted run")
    resume.add_argument("checkpoint", type=Path)

    show = commands.add_parser("show-run", help="print a run checkpoint")
    show.add_argument("checkpoint", type=Path)

    cancel = commands.add_parser("cancel", help="request cancellation of a running analysis")
    cancel.add_argument("run_id")

    decide = commands.add_parser("decide", help="approve or reject a Critic-gated run")
    decide.add_argument("run_id")
    decide.add_argument("action", choices=["approve", "reject"])
    decide.add_argument("--comments", default="")

    recover = commands.add_parser("recover-stale", help="recover interrupted checkpoints")
    recover.add_argument("--older-than-seconds", type=int, default=300)

    search = commands.add_parser("memory-search", help="search historical device cases")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--sensor-type", default="")
    search.add_argument("--mechanism", default="")
    search.add_argument("--outcome", default="")
    search.add_argument("--limit", type=int, default=20)

    verify = commands.add_parser(
        "record-verification", help="attach a physical verification result to a case"
    )
    verify.add_argument("case_id")
    verify.add_argument("vulnerability")
    verify.add_argument("outcome", choices=["confirmed", "rejected", "inconclusive", "not_tested"])
    verify.add_argument("--mechanism", default="")
    verify.add_argument("--notes", default="")
    verify.add_argument("--evidence", default="")

    evaluate = commands.add_parser("evaluate-run", help="evaluate one run against labels")
    evaluate.add_argument("checkpoint", type=Path)
    evaluate.add_argument("case", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = HarnessSettings()

    if args.command == "analyze":
        state = HarnessRunner(settings, profile=args.profile).run(args.input, args.model)
        _print(state.to_dict())
        return 0
    if args.command == "resume":
        state = HarnessRunner(settings).resume(args.checkpoint)
        _print(state.to_dict())
        return 0
    if args.command == "show-run":
        state = CheckpointStore().load(args.checkpoint.expanduser().resolve())
        _print(state.to_dict())
        return 0
    if args.command == "cancel":
        path = HarnessRunner(settings).request_cancel(args.run_id)
        _print({"run_id": args.run_id, "status": "cancel_requested", "marker": str(path)})
        return 0
    if args.command == "decide":
        runner = HarnessRunner(settings)
        state = runner.apply_human_decision(args.run_id, args.action, args.comments)
        if args.action == "approve":
            state = runner.execute(state)
        _print(state.to_dict())
        return 0
    if args.command == "recover-stale":
        states = HarnessRunner(settings).recover_stale_runs(args.older_than_seconds)
        _print([state.to_dict() for state in states])
        return 0

    memory = EpisodicMemoryStore(settings.memory_db)
    if args.command == "memory-search":
        _print(
            memory.search_cases(
                args.query,
                sensor_type=args.sensor_type,
                mechanism=args.mechanism,
                verification_outcome=args.outcome,
                limit=args.limit,
            )
        )
        return 0
    if args.command == "record-verification":
        result_id = memory.record_verification(
            args.case_id,
            args.vulnerability,
            args.outcome,
            mechanism_name=args.mechanism,
            notes=args.notes,
            evidence=args.evidence,
        )
        _print({"verification_result_id": result_id})
        return 0
    if args.command == "evaluate-run":
        benchmark_case = BenchmarkCase.model_validate_json(args.case.read_text(encoding="utf-8"))
        _print(evaluate_run(args.checkpoint, benchmark_case))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
