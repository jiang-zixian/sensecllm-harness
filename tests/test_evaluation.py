from __future__ import annotations

from pathlib import Path

from sensecllm.config import HarnessSettings
from sensecllm.evaluation import (
    BenchmarkCase,
    evaluate_run,
    ndcg_at_k,
    reciprocal_rank,
    retrieval_recall_at_k,
    set_prf,
)
from sensecllm.harness.runner import HarnessRunner

from .test_harness_runner import FakeLegacyAdapter


def test_ranking_and_set_metrics() -> None:
    assert set_prf(["Non-linearity", "aliasing"], ["nonlinearity"])["f1"] == 0.666667
    assert retrieval_recall_at_k(["a", "b", "c"], ["b", "d"], 2) == 0.5
    assert reciprocal_rank(["a", "b", "c"], ["c"]) == 1 / 3
    assert ndcg_at_k(["b", "a"], {"a": 3.0, "b": 1.0}, 2) < 1.0


def test_completed_run_can_be_evaluated(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = HarnessSettings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        memory_db=tmp_path / "runs" / "memory.sqlite3",
        default_model="fake-model",
        retry_backoff_seconds=0.0,
    )
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.run(source)
    benchmark = BenchmarkCase.model_validate(
        {
            "case_id": "mic-001",
            "labels": {
                "sensor_type": "microphone",
                "extraction_fields": {"model": "MIC-001", "sensor_type": "microphone"},
                "mechanisms": ["nonlinearity"],
                "vulnerabilities": ["Ultrasonic injection"],
            },
        }
    )

    result = evaluate_run(Path(state.run_dir) / "checkpoint.json", benchmark)

    assert result["metrics"]["sensor_type_exact_match"] == 1.0
    assert result["metrics"]["mechanisms"]["f1"] == 1.0
    assert result["metrics"]["vulnerabilities"]["f1"] == 1.0
    assert result["metrics"]["extraction_field_f1"] == 1.0
    assert result["metrics"]["evidence_support_precision"] == 1.0
    assert result["metrics"]["unsupported_claim_rate"] == 0.0
    assert (Path(state.run_dir) / "evaluation.mic-001.json").exists()
