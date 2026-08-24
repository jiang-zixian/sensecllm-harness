import json
from typing import Any

from helpers.api.sensor_rag_client import ask_sensor_rag
from helpers.configs.configs import dify_2_analyze_onlyRAG_api_key, output_report
from helpers.utils.file_utils import append_report

from temp_paths import temp_path
from step2_graph.candidate_generator import (
    CandidateExpansionGenerator,
    _compact_state_for_prompt,
    _compact_local_graph_context,
    _compact_operator_context,
    _trim_text,
)
from step2_graph.graph_builder import GraphBuilder
from step2_graph.graph_searcher import MechanismGraphSearcher
from step2_graph.models import SearchConfig, SearchState
from step2_graph.operator_registry import PhysicalOperatorRegistry
from step2_graph.output_adapter import Step2LegacyOutputAdapter, render_legacy_markdown
from step2_graph.path_summarizer import FinalPathSummarizer
from step2_graph.prompts import build_candidate_expansion_prompts
from step2_graph.serialization import dumps_compact


def compress_history_for_analyze(sensor_info: Any) -> str:
    if isinstance(sensor_info, dict):
        sensor_info = json.dumps(sensor_info, ensure_ascii=False, indent=2)
    return "=== Datasheet Sensor Parameters ===\n" + str(sensor_info)


def _read_step1_data() -> dict:
    return json.loads(temp_path("step1_output.json").read_text(encoding="utf-8"))


def _retrieve_rag(rag_input: str) -> str:
    result = ask_sensor_rag(
        question="do the task",
        api_key=dify_2_analyze_onlyRAG_api_key,
        RAGinput=rag_input,
        silent=False,
    )[0]
    if not result:
        raise RuntimeError("Dify returned an empty RAG result")
    return result


def _write_base_prompt_snapshot(rag_result: str, compact_context: str, graph, registry) -> None:
    start_state = SearchState(
        signal_origin="electromagnetic",
        current_node_id="external_electromagnetic",
        visited_node_ids=["external_electromagnetic"],
    )
    state_batch = [("snapshot_state_0", start_state)]
    _, user_prompt = build_candidate_expansion_prompts(
        rag_result=_trim_text(rag_result, 2500),
        compact_context=_trim_text(compact_context, 3500),
        serialized_search_state=dumps_compact(
            [{"state_id": "snapshot_state_0", "state": _compact_state_for_prompt(start_state)}]
        ),
        serialized_sensor_graph="{}",
        serialized_allowed_operators=dumps_compact(_compact_operator_context("entry_expansion")),
        expansion_task="entry_expansion",
        serialized_local_context=dumps_compact(
            _compact_local_graph_context(graph, state_batch, "entry_expansion")
        ),
    )
    temp_path("step2_base_messages.txt").write_text(user_prompt, encoding="utf-8")


def run_step_2(
    model_for_analyze: str = "deepseek-v3.2",
    model_for_verifier: str = "gpt-5.4-mini",
    max_layer_calls: int = 8,
) -> str:
    print("\n---------------------------------第二步 脆弱性机理分析（Physics-Constrained Mechanism Graph Search）----------------------------------")
    step1_data = _read_step1_data()
    rag_input = step1_data["rag_input"]
    sensor_info = step1_data["sensor_info"]

    try:
        rag_result = _retrieve_rag(rag_input)
    except Exception as exc:
        raise RuntimeError(f"机理图搜索阶段 RAG 检索失败：{exc}") from exc

    compact_context = compress_history_for_analyze(sensor_info=sensor_info)
    temp_path("step2_compact_context.txt").write_text(compact_context, encoding="utf-8")
    temp_path("step2_rag_result.txt").write_text(rag_result, encoding="utf-8")

    # Keep the Step1 class hint (rag_input) together with the detailed sensor
    # description.  Passing only sensor_info can make a pressure sensor that
    # mentions "light sensitivity" look like an optical sensor, which filters
    # the optical cross-field origin before graph search starts.
    graph = GraphBuilder().build(step1_data)
    registry = PhysicalOperatorRegistry()
    _write_base_prompt_snapshot(rag_result, compact_context, graph, registry)

    progress_events = []

    def record_progress(event: dict) -> None:
        progress_events.append(event)
        temp_path("step2_llm_progress.json").write_text(
            json.dumps(progress_events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        event_name = str(event.get("event") or "progress")
        details = []
        for key in (
            "layer_call",
            "frontier_size",
            "attempt",
            "max_attempts",
            "raw_candidate_count",
            "candidate_count",
            "invalid_candidate_count",
            "failed_chunk_count",
            "api_attempt_count",
            "retry_delay_seconds",
        ):
            if key in event:
                details.append(f"{key}={event[key]}")
        if event.get("error"):
            details.append(f"error={event['error']}")
        print(
            f"[Step2-Progress] {event_name} " + " ".join(details),
            flush=True,
        )

    generator = CandidateExpansionGenerator(
        model=model_for_analyze,
        rag_result=rag_result,
        compact_context=compact_context,
        progress_callback=record_progress,
    )
    searcher = MechanismGraphSearcher(
        graph=graph,
        generator=generator,
        registry=registry,
        config=SearchConfig(
            max_depth=max_layer_calls,
            beam_width=24,
            max_paths_per_signal=12,
            max_llm_expansions=max_layer_calls,
            accepted_path_limit=36,
        ),
    )
    paths_payload = searcher.search()
    paths_payload["candidate_generator_errors"] = generator.errors
    paths_payload["prompt_records"] = generator.prompt_records
    paths_payload["llm_candidate_records"] = generator.response_records
    paths_payload["llm_call_count"] = generator.calls
    paths_payload["llm_api_attempt_count"] = generator.api_attempts
    paths_payload["llm_error_count"] = len(generator.errors)
    paths_payload["final_path_summaries"] = FinalPathSummarizer().summarize(paths_payload)

    temp_path("step2_mechanism_paths.json").write_text(
        json.dumps(paths_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path("step2_graph_search_log.json").write_text(
        json.dumps(searcher.logs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    legacy_payload = Step2LegacyOutputAdapter().adapt(paths_payload)
    legacy_json = json.dumps(legacy_payload, ensure_ascii=False, indent=2)
    temp_path("step2_output.json").write_text(legacy_json, encoding="utf-8")
    temp_path("step2_output.txt").write_text(legacy_json, encoding="utf-8")
    temp_path("step2_legacy_markdown.md").write_text(render_legacy_markdown(legacy_payload), encoding="utf-8")

    print(
        "[Step2-Graph] accepted_paths="
        f"{len(paths_payload.get('accepted_paths', []))}, "
        f"unresolved_paths={len(paths_payload.get('unresolved_paths', []))}, "
        f"rejected_paths={len(paths_payload.get('rejected_paths', []))}, "
        f"legacy_mechanisms={len(legacy_payload.get('mechanisms', []))}"
    )
    append_report(output_report, "\n" + legacy_json + "\n")
    return legacy_json


if __name__ == "__main__":
    run_step_2()
