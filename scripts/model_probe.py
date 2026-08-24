from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

from sensecllm.models.chatanywhere import ChatAnywhereGateway
from sensecllm.observability.usage import summarize_usage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", help="ChatAnywhere model identifiers")
    parser.add_argument("--output", type=Path, default=Path("evals/results/model-probe.json"))
    args = parser.parse_args()
    usage = args.output.with_suffix(".usage.jsonl")
    if usage.exists():
        usage.unlink()
    results = []
    for model in args.models:
        started = time.monotonic()
        try:
            response = ChatAnywhereGateway(usage_file=usage).complete_json(
                model=model,
                system_prompt="Return strict JSON only.",
                user_prompt=(
                    "For a sensor-security harness, return an object with keys "
                    "mechanism and evidence_policy. Use mechanism=nonlinearity and state that "
                    "historical cases are priors, not target evidence."
                ),
            )
            results.append(
                {
                    "model": model,
                    "status": "ok",
                    "latency_seconds": round(time.monotonic() - started, 3),
                    "schema_valid": bool(response.get("mechanism") and response.get("evidence_policy")),
                }
            )
        except (requests.RequestException, RuntimeError, TypeError, ValueError) as exc:
            results.append(
                {
                    "model": model,
                    "status": "failed",
                    "latency_seconds": round(time.monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                }
            )
    payload = {"scope": "gateway schema/latency probe; not task-quality evaluation", "results": results, "usage": summarize_usage(usage)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if any(item["status"] == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
