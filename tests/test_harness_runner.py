from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest

from sensecllm.config import HarnessSettings
from sensecllm.harness.runner import HarnessRunner
from sensecllm.harness.state import RunStatus, StageStatus
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.observability.usage import record_model_usage


class FakeLegacyAdapter:
    def __init__(
        self,
        _project_root: Path,
        _input_path: Path,
        report_path: Path,
        failures: dict[str, int] | None = None,
    ) -> None:
        self.report_path = report_path
        self.data_dir = report_path.parent / "temp_data" / report_path.stem
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.failures = failures if failures is not None else {}

    def run_stage(self, stage: str, _model: str):
        remaining = self.failures.get(stage, 0)
        if remaining:
            self.failures[stage] = remaining - 1
            raise RuntimeError(f"planned {stage} failure")
        if stage == "document":
            self._write(
                "step1_output.json",
                {
                    "rag_input": "MEMS microphone",
                    "sensor_info": {"model": "MIC-001", "sensor_type": "microphone"},
                },
            )
        elif stage == "mechanism":
            self._write(
                "step2_mechanism_paths.json",
                {
                    "sensor_model": "MIC-001",
                    "accepted_paths": [
                        {
                            "path_id": "path-1",
                            "status": "accepted",
                            "path_score": 0.9,
                            "mechanism_instances": [
                                {
                                    "mechanism_name": "nonlinearity",
                                    "source_component": "MEMS transducer",
                                }
                            ],
                        }
                    ],
                },
            )
        elif stage == "vulnerability":
            self._write(
                "step3_vulnerability_items.json",
                [
                    {
                        "vulnerability_name": "Ultrasonic injection",
                        "mechanism_name": "nonlinearity",
                        "source_component": "MEMS transducer",
                    }
                ],
            )
        elif stage == "experiment":
            self._write(
                "step4_single_results.json",
                [
                    {
                        "vulnerability_name": "Ultrasonic injection",
                        "mechanism_name": "nonlinearity",
                        "verification_plans": [{"parameter_confidence": "high"}],
                    }
                ],
            )
        elif stage == "defense":
            self.report_path.write_text("# report", encoding="utf-8")
        return {"stage": stage}

    def _write(self, name: str, payload) -> None:
        (self.data_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _settings(tmp_path: Path) -> HarnessSettings:
    return HarnessSettings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        memory_db=tmp_path / "runs" / "memory.sqlite3",
        default_model="fake-model",
        retry_backoff_seconds=0.0,
    )


def test_run_persists_checkpoint_events_and_episode(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = _settings(tmp_path)
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )

    state = runner.run(source)

    assert state.status == RunStatus.COMPLETED
    assert all(record.status == StageStatus.COMPLETED for record in state.stages.values())
    assert (Path(state.run_dir) / "checkpoint.json").exists()
    assert (Path(state.run_dir) / "events.jsonl").exists()
    assert state.metadata["episodic_case_id"]
    cases = runner.memory.search_cases("MIC-001", mechanism="nonlinearity")
    assert len(cases) == 1
    case = runner.memory.get_case(cases[0]["id"])
    assert case is not None
    assert {item["kind"] for item in case["findings"]} == {
        "experiment_plan",
        "mechanism_path",
        "vulnerability",
    }


def test_resume_skips_completed_agents(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = _settings(tmp_path)
    failures = {"mechanism": 1}
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path, failures
        ),
    )
    state = runner.create_run(source)

    with pytest.raises(RuntimeError, match="planned mechanism failure"):
        runner.execute(state)

    checkpoint = Path(state.run_dir) / "checkpoint.json"
    resumed = runner.resume(checkpoint)
    assert resumed.status == RunStatus.COMPLETED
    assert resumed.stages["document"].status == StageStatus.COMPLETED
    assert resumed.stages["mechanism"].status == StageStatus.COMPLETED


def test_verification_outcome_is_queryable(tmp_path: Path) -> None:
    memory = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    # Reuse a completed synthetic run to obtain a valid case.
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
        memory=memory,
    )
    state = runner.run(source)
    case_id = state.metadata["episodic_case_id"]

    memory.record_verification(
        case_id,
        "Ultrasonic injection",
        "confirmed",
        mechanism_name="nonlinearity",
        notes="Observed repeatable output deviation",
    )

    cases = memory.search_cases(verification_outcome="confirmed")
    assert [case["id"] for case in cases] == [case_id]


def test_second_run_recalls_first_episode(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )

    first = runner.run(source)
    second = runner.run(source)

    recalled_ids = {case["run_id"] for case in second.metadata["similar_cases"]}
    assert first.run_id in recalled_ids
    ranked = second.metadata["similar_cases_ranked"]
    assert ranked[0]["run_id"] == first.run_id
    assert ranked[0]["mechanism_overlap"] == ["nonlinearity"]


def test_critic_routes_mismatched_mechanism_to_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MismatchAdapter(FakeLegacyAdapter):
        def run_stage(self, stage: str, model: str):
            result = super().run_stage(stage, model)
            if stage == "vulnerability":
                self._write(
                    "step3_vulnerability_items.json",
                    [
                        {
                            "vulnerability_name": "Unsupported hypothesis",
                            "mechanism_name": "resonance",
                            "source_component": "MEMS transducer",
                        }
                    ],
                )
            return result

    monkeypatch.delenv("CHATANYWHERE_API_KEY", raising=False)
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: MismatchAdapter(
            root, input_path, report_path
        ),
    )

    waiting = runner.run(source)

    assert waiting.status == RunStatus.WAITING_APPROVAL
    assert waiting.metadata["critic_decision"] == "review"
    assert waiting.metadata["requires_human_review"] is True
    review = json.loads((waiting.data_dir / "critic_review.json").read_text(encoding="utf-8"))
    assert review["llm_review"]["status"] == "skipped_no_api_key"

    approved = runner.apply_human_decision(waiting.run_id, "approve", "reviewed")
    completed = runner.execute(approved)
    assert completed.status == RunStatus.COMPLETED
    assert completed.metadata["human_decision"]["action"] == "approve"


def test_cancelled_run_can_be_resumed(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.create_run(source)
    runner.request_cancel(state.run_id)

    cancelled = runner.execute(state)
    assert cancelled.status == RunStatus.CANCELLED

    resumed = runner.resume(Path(state.run_dir) / "checkpoint.json")
    assert resumed.status == RunStatus.COMPLETED


def test_transient_agent_failure_is_retried(tmp_path: Path) -> None:
    class TransientAdapter(FakeLegacyAdapter):
        def run_stage(self, stage: str, model: str):
            if stage == "mechanism" and not getattr(self, "failed_once", False):
                self.failed_once = True
                raise RuntimeError("HTTP 503 temporarily unavailable")
            return super().run_stage(stage, model)

    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: TransientAdapter(
            root, input_path, report_path
        ),
    )

    state = runner.run(source)

    assert state.status == RunStatus.COMPLETED
    assert state.stages["mechanism"].attempts == 2
    assert state.metadata["usage"]["retry_count"] == 1


def test_total_attempt_budget_stops_run(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = replace(_settings(tmp_path), max_total_agent_attempts=1)
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )

    with pytest.raises(RuntimeError, match="attempt budget exhausted"):
        runner.run(source)


def test_stale_running_checkpoint_is_recoverable(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.create_run(source)
    state.status = RunStatus.RUNNING
    state.current_stage = "document"
    state.stages["document"].status = StageStatus.RUNNING
    checkpoint = runner.checkpoints.save(state)
    old = time.time() - 600
    os.utime(checkpoint, (old, old))

    recovered = runner.recover_stale_runs(older_than_seconds=300)

    assert [item.run_id for item in recovered] == [state.run_id]
    assert recovered[0].status == RunStatus.FAILED
    assert recovered[0].stages["document"].failure_class == "transient"


def test_human_revision_reruns_critic_and_completes(tmp_path: Path, monkeypatch) -> None:
    class MismatchAdapter(FakeLegacyAdapter):
        def run_stage(self, stage: str, model: str):
            result = super().run_stage(stage, model)
            if stage == "vulnerability":
                self._write(
                    "step3_vulnerability_items.json",
                    [{"vulnerability_name": "bad", "mechanism_name": "resonance"}],
                )
            return result

    monkeypatch.delenv("CHATANYWHERE_API_KEY", raising=False)
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: MismatchAdapter(
            root, input_path, report_path
        ),
    )
    waiting = runner.run(source)
    revised = runner.apply_human_decision(
        waiting.run_id,
        "revise",
        "corrected",
        [
            {
                "vulnerability_name": "Ultrasonic injection",
                "mechanism_name": "nonlinearity",
                "source_component": "MEMS transducer",
            }
        ],
    )
    completed = runner.execute(revised)
    assert completed.status == RunStatus.COMPLETED
    assert completed.metadata["critic_decision"] == "approve"


def test_run_writes_structured_agent_traces(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.run(source)
    spans = [
        json.loads(line)
        for line in (Path(state.run_dir) / "traces.jsonl").read_text().splitlines()
    ]
    assert len(spans) == len(state.stages)
    assert {span["trace_id"] for span in spans} == {state.run_id}


def test_conversation_memory_round_trip(tmp_path: Path) -> None:
    memory = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    memory.add_message("run-1", "user", "what evidence?")
    memory.add_message(
        "run-1", "assistant", "artifact evidence", [{"source": "report.md", "chunk": "0"}]
    )
    messages = memory.list_messages("run-1")
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["citations"][0]["source"] == "report.md"


def test_single_agent_ablation_profile_runs_same_domain_stages(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        profile="single_agent",
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.run(source)
    assert state.status == RunStatus.COMPLETED
    assert list(state.stages) == ["single_agent"]
    assert Path(state.report_path).exists()


def test_model_token_budget_stops_before_next_agent(tmp_path: Path) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = replace(_settings(tmp_path), max_model_tokens=1)
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.create_run(source)
    record_model_usage(
        Path(state.run_dir) / "usage.jsonl",
        provider="test",
        model="fake-model",
        usage={"total_tokens": 2},
    )
    runner._update_model_usage(state)
    with pytest.raises(RuntimeError, match="model token budget exceeded"):
        runner.execute(state)


def test_critic_applies_schema_normalized_llm_revision(tmp_path: Path, monkeypatch) -> None:
    class MismatchAdapter(FakeLegacyAdapter):
        def run_stage(self, stage: str, model: str):
            result = super().run_stage(stage, model)
            if stage == "vulnerability":
                self._write(
                    "step3_vulnerability_items.json",
                    [{"vulnerability_name": "bad", "mechanism_name": "resonance"}],
                )
            return result

    monkeypatch.setenv("CHATANYWHERE_API_KEY", "test-key")
    monkeypatch.setattr(
        "sensecllm.models.chatanywhere.ChatAnywhereGateway.complete_json",
        lambda *_args, **_kwargs: {
            "decision": "revise",
            "issues": [],
            "rationale": "canonical correction",
            "revised_vulnerabilities": [
                {
                    "title": "Ultrasonic injection",
                    "mechanism": "nonlinearity effect",
                    "entry_point": "MEMS transducer",
                }
            ],
        },
    )
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: MismatchAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.run(source)
    assert state.status == RunStatus.COMPLETED
    assert state.metadata["critic_decision"] == "approve"
    revised = json.loads(
        (state.data_dir / "step3_vulnerability_items.json").read_text(encoding="utf-8")
    )
    assert revised[0]["mechanism_name"] == "nonlinearity effect"
    assert revised[0]["source_component"] == "MEMS transducer"


def test_critic_reject_stops_downstream_agents(tmp_path: Path, monkeypatch) -> None:
    class MismatchAdapter(FakeLegacyAdapter):
        def run_stage(self, stage: str, model: str):
            result = super().run_stage(stage, model)
            if stage == "vulnerability":
                self._write(
                    "step3_vulnerability_items.json",
                    [{"vulnerability_name": "bad", "mechanism_name": "resonance"}],
                )
            return result

    monkeypatch.setenv("CHATANYWHERE_API_KEY", "test-key")
    monkeypatch.setattr(
        "sensecllm.models.chatanywhere.ChatAnywhereGateway.complete_json",
        lambda *_args, **_kwargs: {"decision": "reject", "issues": [], "rationale": "unsafe"},
    )
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    runner = HarnessRunner(
        _settings(tmp_path),
        adapter_factory=lambda root, input_path, report_path: MismatchAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.run(source)
    assert state.status == RunStatus.REJECTED
    assert state.stages["experiment"].status == StageStatus.PENDING
