from __future__ import annotations

import json
from pathlib import Path

from sensecllm.chat import PostAnalysisChatService
from sensecllm.harness.state import RunState, RunStatus
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.models.chatanywhere import ChatAnywhereGateway


def _state(tmp_path: Path) -> RunState:
    run_dir = tmp_path / "runs" / "abc123"
    report_path = run_dir / "report.md"
    data_dir = run_dir / "temp_data" / "report"
    data_dir.mkdir(parents=True)
    report_path.write_text("# Report\n\nUltrasonic injection affects MEMS microphones.", encoding="utf-8")
    (data_dir / "step1_output.json").write_text(
        json.dumps(
            {
                "rag_input": "MEMS microphone",
                "sensor_info": {"model": "MIC-001", "sensor_type": "microphone"},
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "step2_mechanism_paths.json").write_text(
        json.dumps(
            {
                "sensor_model": "MIC-001",
                "accepted_paths": [
                    {
                        "path_id": "path-1",
                        "status": "accepted",
                        "path_score": 0.91,
                        "mechanism_instances": [
                            {
                                "mechanism_name": "nonlinearity",
                                "source_component": "MEMS transducer",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "step3_vulnerability_items.json").write_text(
        json.dumps(
            [
                {
                    "vulnerability_name": "Ultrasonic injection",
                    "mechanism_name": "nonlinearity",
                    "source_component": "MEMS transducer",
                }
            ]
        ),
        encoding="utf-8",
    )
    (data_dir / "step4_single_results.json").write_text("[]", encoding="utf-8")
    return RunState(
        run_id="abc123",
        input_path=str(tmp_path / "sensor.md"),
        run_dir=str(run_dir),
        report_path=str(report_path),
        model="fake-model",
        status=RunStatus.COMPLETED,
    )


def test_post_analysis_chat_gathers_open_question_context(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("CHATANYWHERE_API_KEY", raising=False)
    state = _state(tmp_path)
    memory = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    state.metadata["episodic_case_id"] = memory.remember_run(state)
    memory.add_message(state.run_id, "assistant", "Earlier grounded answer")

    def fake_rag(_question: str) -> list[dict]:
        return [
            {
                "source_type": "paper",
                "source": "paper-a",
                "chunk": "0",
                "content": "Paper evidence",
            },
            {
                "source_type": "web",
                "source": "https://example.test",
                "chunk": "1",
                "content": "Web snippet",
            },
        ]

    result = PostAnalysisChatService(memory, rag_retriever=fake_rag).ask(
        state,
        "结合历史案例、论文和网络证据，这个结论充分吗？",
    )

    assert result["mode"] == "post_analysis"
    assert result["plan"]["needs_memory"] is True
    assert result["plan"]["needs_rag"] is True
    assert result["plan"]["needs_web"] is True
    source_types = {item["source_type"] for item in result["evidence_sources"]}
    assert {"artifact", "conversation", "memory", "paper", "web"} <= source_types


def test_post_analysis_chat_keeps_artifacts_and_filters_citations(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CHATANYWHERE_API_KEY", "test-key")
    state = _state(tmp_path)
    memory = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    calls = {"count": 0}

    def fake_complete_json(self, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "intent": "answer_from_memory_only",
                "needs_artifacts": False,
                "needs_conversation": False,
                "needs_memory": False,
                "needs_rag": False,
                "needs_web": False,
                "needs_critic": False,
                "answer_style": "concise",
                "reason": "test",
            }
        return {
            "answer": "The run artifact supports the answer.",
            "citations": [
                {"source_type": "artifact", "source": "report.md", "chunk": "0"},
                {"source_type": "web", "source": "https://not-allowed.test", "chunk": "9"},
            ],
        }

    monkeypatch.setattr(ChatAnywhereGateway, "complete_json", fake_complete_json)
    result = PostAnalysisChatService(memory, rag_retriever=lambda _question: []).ask(
        state,
        "这个报告结论是什么？",
    )

    assert result["plan"]["needs_artifacts"] is True
    assert result["answer"] == "The run artifact supports the answer."
    assert result["citations"] == [
        {"source_type": "artifact", "source": "report.md", "chunk": "0"}
    ]


def test_post_analysis_chat_observes_and_replans(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHATANYWHERE_API_KEY", "test-key")
    run_dir = tmp_path / "runs" / "empty"
    state = RunState(
        run_id="empty",
        input_path=str(tmp_path / "sensor.md"),
        run_dir=str(run_dir),
        report_path=str(run_dir / "report.md"),
        model="fake-model",
        status=RunStatus.COMPLETED,
    )
    memory = EpisodicMemoryStore(tmp_path / "memory.sqlite3")
    calls = {"count": 0}

    def fake_complete_json(self, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "intent": "check_latest_context",
                "needs_artifacts": True,
                "needs_conversation": True,
                "needs_memory": False,
                "needs_rag": True,
                "needs_web": True,
                "needs_critic": False,
                "answer_style": "concise",
                "reason": "Need web context",
            }
        if calls["count"] == 2:
            return {
                "intent": "answer_from_available_context",
                "needs_artifacts": True,
                "needs_conversation": True,
                "needs_memory": False,
                "needs_rag": False,
                "needs_web": False,
                "needs_critic": False,
                "answer_style": "concise",
                "reason": "Web unavailable; answer from observed conversation",
            }
        return {
            "answer": "Web evidence was unavailable, so only conversation context was used.",
            "citations": [
                {
                    "source_type": "conversation",
                    "source": "conversation_messages",
                    "chunk": "0",
                }
            ],
        }

    monkeypatch.setattr(ChatAnywhereGateway, "complete_json", fake_complete_json)
    result = PostAnalysisChatService(memory, rag_retriever=lambda _question: []).ask(
        state,
        "请结合网络最新信息解释这个结论",
    )

    assert len(result["plans"]) == 2
    assert len(result["observations"]) == 2
    assert result["observations"][0]["missing_sources"] == ["rag", "web"]
    assert result["observations"][0]["should_replan"] is True
    assert result["observations"][1]["should_replan"] is False
    assert calls["count"] == 3
