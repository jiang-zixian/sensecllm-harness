import re
from typing import Any, Dict, Iterable, List, Sequence


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "<br>".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return "<br>".join(
            f"{_text(key)}: {_text(val)}" for key, val in value.items() if _text(val)
        )
    return str(value).strip()


def _cell(value: Any) -> str:
    text = _text(value)
    text = re.sub(r"\s*\n+\s*", "<br>", text)
    text = re.sub(r"\s+", " ", text)
    return text.replace("|", "\\|")


def _numbered_list(items: Any) -> str:
    if isinstance(items, str):
        items = [line.strip() for line in items.splitlines() if line.strip()]
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        items = [items]
    normalized = []
    for idx, item in enumerate(items, start=1):
        text = _text(item)
        if not text:
            continue
        text = re.sub(r"^\s*\d+[\.)]\s*", "", text)
        normalized.append(f"{idx}. {text}")
    return "<br>".join(normalized)


def _bullet_list(items: Any) -> str:
    if isinstance(items, str):
        items = [line.strip() for line in items.splitlines() if line.strip()]
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        items = [items]
    normalized = []
    for item in items:
        text = _text(item)
        if text:
            normalized.append(text)
    return "<br>".join(f"{idx}. {item}" for idx, item in enumerate(normalized, start=1))


def _format_evidence(evidence: Any) -> str:
    if isinstance(evidence, dict):
        evidence = [evidence]
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return _text(evidence)

    normalized = []
    for entry in evidence:
        if isinstance(entry, dict):
            source = _text(entry.get("source"))
            summary = _text(entry.get("summary"))
            if source and summary:
                normalized.append(f"{source}: {summary}")
            elif source or summary:
                normalized.append(source or summary)
            continue
        text = _text(entry)
        if text:
            normalized.append(text)
    return "<br>".join(f"{idx}. {item}" for idx, item in enumerate(normalized, start=1))


def _strip_markdown_heading(line: str) -> str:
    return re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip()


def _strip_list_marker(line: str) -> str:
    return re.sub(r"^\s*[-*+]\s*", "", line).strip()


def render_sensor_info(step1_data: Dict[str, Any]) -> str:
    sensor_info = step1_data.get("sensor_info", {})
    lines = ["### Sensor Information", ""]

    if isinstance(sensor_info, dict):
        for key, value in sensor_info.items():
            text = _text(value)
            if text:
                lines.append(f"- {_strip_markdown_heading(_text(key))}: {text}")
    else:
        raw_lines = _text(sensor_info).splitlines()
        for raw_line in raw_lines:
            line = _strip_markdown_heading(_strip_list_marker(raw_line))
            if not line or line.lower() == "sensor information":
                continue
            lines.append(f"- {line}")

    if step1_data.get("rag_input"):
        lines.append(f"- RAG Input: {_text(step1_data.get('rag_input'))}")

    return "\n".join(lines).rstrip() + "\n"


def render_vulnerability_detection(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "### Vulnerability Detection\n\nNo vulnerabilities detected after filtering.\n"

    lines = [
        "### Vulnerability Detection",
        "",
        "| No. | Vulnerability Name | Mechanism Name | Source Component | Description | Judgment Reason | Evidence |",
        "|:---:|:---|:---|:---|:---|:---|:---|",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(idx),
                    _cell(item.get("vulnerability_name")),
                    _cell(item.get("mechanism_name")),
                    _cell(item.get("source_component")),
                    _cell(item.get("description")),
                    _cell(item.get("judgment_reason")),
                    _cell(_format_evidence(item.get("evidence"))),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _format_attack_parameters(plan: Dict[str, Any]) -> str:
    parts = []
    modality = _text(plan.get("attack_signal_modality"))
    if modality:
        parts.append(f"Modality: {modality}")

    freq_range = plan.get("attack_freq_range")
    unit = _text(plan.get("attack_freq_unit"))
    if isinstance(freq_range, Sequence) and not isinstance(freq_range, (str, bytes)) and len(freq_range) >= 2:
        parts.append(f"Frequency range: {freq_range[0]}-{freq_range[1]} {unit}".strip())
    elif freq_range:
        parts.append(f"Frequency range: {_text(freq_range)} {unit}".strip())

    parameter_range = _text(plan.get("attack_signal_parameter_range"))
    if parameter_range:
        parts.append(f"Other parameters: {parameter_range}")

    extra_keys = [
        key
        for key in sorted(plan.keys())
        if key
        not in {
            "vulnerability_name",
            "required_testing_equipment",
            "attack_signal_modality",
            "attack_freq_range",
            "attack_freq_unit",
            "attack_signal_parameter_range",
            "testing_steps",
            "expected_result",
            "reasoning_for_parameter_inference",
            "evidence",
        }
    ]
    for key in extra_keys:
        value = _text(plan.get(key))
        if value:
            parts.append(f"{key}: {value}")

    return "<br>".join(parts)


def _format_reasoning(result: Dict[str, Any], plan: Dict[str, Any]) -> str:
    explicit = _text(plan.get("reasoning_for_parameter_inference"))
    if explicit:
        return explicit

    item = result.get("source_vulnerability_item", {}) or {}
    parts = []
    if item.get("source_component") or item.get("mechanism_name"):
        parts.append(
            "Source component/mechanism: "
            + ", ".join(
                part
                for part in [
                    _text(item.get("source_component")),
                    _text(item.get("mechanism_name")),
                ]
                if part
            )
        )
    if item.get("judgment_reason"):
        parts.append(_text(item.get("judgment_reason")))
    attack_parameters = _format_attack_parameters(plan)
    if attack_parameters:
        parts.append("Verified attack parameters are taken from the validated plan: " + attack_parameters.replace("<br>", "; "))
    return " ".join(parts)


def iter_verification_plan_rows(single_results: Iterable[Dict[str, Any]]):
    row_no = 1
    for result in single_results:
        plans = result.get("verification_plans") or []
        if not isinstance(plans, list):
            plans = [plans]
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            yield row_no, result, plan
            row_no += 1


def render_physical_verification(single_results: List[Dict[str, Any]]) -> str:
    rows = list(iter_verification_plan_rows(single_results))
    if not rows:
        return "### Physical Verification\n\nNo valid physical verification plans generated.\n"

    lines = [
        "### Physical Verification",
        "",
        "| No. | Vulnerability Name | Required Testing Equipment | Attack signal parameter range(External signals used by attackers) | Testing Steps and Data | Expected Result | Reasoning for parameter inference | Evidence |",
        "|:---:|:---|:---|:---|:---|:---|:---|:---|",
    ]
    for row_no, result, plan in rows:
        vuln_name = plan.get("vulnerability_name") or result.get("vulnerability_name")
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(row_no),
                    _cell(vuln_name),
                    _cell(_bullet_list(plan.get("required_testing_equipment"))),
                    _cell(_format_attack_parameters(plan)),
                    _cell(_numbered_list(plan.get("testing_steps"))),
                    _cell(plan.get("expected_result")),
                    _cell(_format_reasoning(result, plan)),
                    _cell(_format_evidence(plan.get("evidence"))),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_defense_recommendations(defense_items: List[Dict[str, Any]]) -> str:
    if not defense_items:
        return "### Defense Recommendations\n\nNo vulnerabilities available for defense recommendation generation.\n"

    lines = [
        "### Defense Recommendations",
        "",
        "| No. | Vulnerability | Exploitation Path | Critical Propagation Edge | Vulnerability Principle | Edge-linked Defense Recommendation |",
        "|:---:|:---|:---|:---|:---|:---|",
    ]
    for idx, item in enumerate(defense_items, start=1):
        edge = item.get("critical_edge") or {}
        if item.get("traceability_status") != "Step 3 path and mechanism edge linked":
            path = item.get("path_id") or "No Step 3 supporting path available"
            critical_edge = "Not available"
            recommendation = "No recommendation emitted because it cannot be traced through the Step 3 path lineage to a mechanism-bearing edge."
        else:
            path = (
                f"{item.get('path_id')} [{item.get('path_status')}] "
                f"({item.get('external_modality')} -> {item.get('observable_output')})"
                f"<br>{item.get('path_trace')}"
            )
            critical_edge = (
                f"{edge.get('edge_id')}: {edge.get('source_node')} --[{edge.get('relation_type')}]--> "
                f"{edge.get('target_node')}"
            )
            recommendation = item.get("recommendation")
            if item.get("verification_context"):
                recommendation = f"{recommendation} {item.get('verification_context')}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(idx),
                    _cell(f"{item.get('vulnerability_name')} ({item.get('mechanism_name')})"),
                    _cell(path),
                    _cell(critical_edge),
                    _cell(item.get("principle")),
                    _cell(recommendation),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
