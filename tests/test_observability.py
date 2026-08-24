from pathlib import Path

from sensecllm.observability.metrics import collect_metrics, prometheus_metrics
from sensecllm.observability.usage import record_model_usage, summarize_usage


def test_usage_accounting_and_prometheus_output(tmp_path: Path) -> None:
    usage = tmp_path / "usage.jsonl"
    record_model_usage(
        usage,
        provider="chatanywhere",
        model="deepseek-v3.2",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    summary = summarize_usage(usage)
    assert summary["total_tokens"] == 15
    metrics = collect_metrics(tmp_path / "runs")
    assert "sensecllm_runs_total 0" in prometheus_metrics(metrics)
