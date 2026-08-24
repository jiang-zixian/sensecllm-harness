from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sensecllm.harness.checkpoint import CheckpointStore

from .metrics import normalize_label, set_prf
from .models import BenchmarkCase


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _first(mapping: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def evaluate_run(checkpoint_path: Path, benchmark_case: BenchmarkCase) -> dict[str, Any]:
    state = CheckpointStore().load(checkpoint_path.expanduser().resolve())
    step1 = _read_json(state.data_dir / "step1_output.json", {})
    graph = _read_json(state.data_dir / "step2_mechanism_paths.json", {})
    vulnerabilities = _read_json(state.data_dir / "step3_vulnerability_items.json", [])
    experiments = _read_json(state.data_dir / "step4_single_results.json", [])
    constraint_traces = _read_json(state.data_dir / "step4_constraint_traces.json", [])

    sensor_info = step1.get("sensor_info", {}) if isinstance(step1, dict) else {}
    predicted_sensor_type = _first(
        sensor_info,
        ("sensor_type", "type", "category", "传感器类型", "类型"),
    ) or str(step1.get("rag_input") or "" if isinstance(step1, dict) else "")

    accepted = graph.get("accepted_paths", []) if isinstance(graph, dict) else []
    predicted_mechanisms: list[str] = []
    for path in accepted if isinstance(accepted, list) else []:
        if not isinstance(path, dict):
            continue
        for item in path.get("mechanism_instances") or []:
            if isinstance(item, dict) and item.get("mechanism_name"):
                predicted_mechanisms.append(str(item["mechanism_name"]))
    predicted_vulnerabilities = (
        [
            str(item.get("vulnerability_name") or item.get("name") or "")
            for item in vulnerabilities
            if isinstance(item, dict)
        ]
        if isinstance(vulnerabilities, list)
        else []
    )

    unresolved = graph.get("unresolved_paths", []) if isinstance(graph, dict) else []
    rejected = graph.get("rejected_paths", []) if isinstance(graph, dict) else []
    expected = benchmark_case.labels
    predicted_fields = {
        key: str(sensor_info.get(key) or "") for key in expected.extraction_fields
    }
    field_metric = set_prf(
        [f"{key}:{value}" for key, value in predicted_fields.items() if value],
        [f"{key}:{value}" for key, value in expected.extraction_fields.items() if value],
    )
    supported = 0
    claim_count = 0
    accepted_mechanisms = {normalize_label(item) for item in predicted_mechanisms}
    for item in vulnerabilities if isinstance(vulnerabilities, list) else []:
        if not isinstance(item, dict):
            continue
        claim_count += 1
        evidence_values = [
            item.get(key)
            for key in (
                "evidence",
                "evidence_refs",
                "citations",
                "source_path",
                "path_id",
                "references",
                "exploitable_parameters",
            )
        ]
        raw_mechanism = str(item.get("mechanism_name") or item.get("mechanism") or "")
        mechanism_supported = any(
            normalize_label(part) in accepted_mechanisms for part in raw_mechanism.split(",")
        )
        has_linkage = any(evidence_values) or (
            item.get("mechanism_name") and item.get("source_component")
        )
        if mechanism_supported and has_linkage:
            supported += 1
    plans: list[dict[str, Any]] = []
    for item in experiments if isinstance(experiments, list) else []:
        if isinstance(item, dict):
            raw = item.get("verification_plans") or item.get("plans") or [item]
            plans.extend(plan for plan in raw if isinstance(plan, dict))
    constrained = sum(
        bool(
            plan.get("constraints")
            or plan.get("safety_constraints")
            or plan.get("parameter_range")
            or plan.get("attack_signal_parameter_range")
            or plan.get("attack_freq_range")
            or (plan.get("min") is not None and plan.get("max") is not None)
        )
        for plan in plans
    )
    if isinstance(constraint_traces, list) and constraint_traces:
        constraint_total = len(constraint_traces)
        constraint_passed = sum(
            not trace.get("error")
            and int(trace.get("compiled_plan_count") or 0) > 0
            and bool(trace.get("supporting_path_ids"))
            for trace in constraint_traces
            if isinstance(trace, dict)
        )
    else:
        constraint_total = len(plans)
        constraint_passed = constrained
    result = {
        "schema_version": "1.0",
        "case_id": benchmark_case.case_id,
        "run_id": state.run_id,
        "split": benchmark_case.split,
        "predictions": {
            "sensor_type": predicted_sensor_type,
            "mechanisms": sorted(set(predicted_mechanisms)),
            "vulnerabilities": sorted(set(predicted_vulnerabilities)),
            "extraction_fields": predicted_fields,
        },
        "metrics": {
            "sensor_type_exact_match": float(
                normalize_label(predicted_sensor_type) == normalize_label(expected.sensor_type)
            ),
            "mechanisms": set_prf(predicted_mechanisms, expected.mechanisms),
            "vulnerabilities": set_prf(predicted_vulnerabilities, expected.vulnerabilities),
            "extraction_fields": field_metric,
            "extraction_field_f1": field_metric["f1"],
            "evidence_support_precision": round(supported / claim_count, 6)
            if claim_count
            else 1.0,
            "unsupported_claim_rate": round((claim_count - supported) / claim_count, 6)
            if claim_count
            else 0.0,
            "experiment_constraint_pass_rate": round(
                constraint_passed / constraint_total, 6
            )
            if constraint_total
            else 1.0,
        },
        "path_counts": {
            "accepted": len(accepted),
            "unresolved": len(unresolved) if isinstance(unresolved, list) else 0,
            "rejected": len(rejected) if isinstance(rejected, list) else 0,
        },
        "operational": {
            "status": state.status.value,
            "model": state.model,
            "critic_decision": state.metadata.get("critic_decision"),
            "usage": state.metadata.get("usage", {}),
        },
    }
    output = Path(state.run_dir) / f"evaluation.{benchmark_case.case_id}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
