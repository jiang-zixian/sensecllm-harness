import json
import re
from typing import Any, Dict, List

from helpers.configs.configs import output_report
from helpers.utils.file_utils import append_report
from report_renderers import render_defense_recommendations
from temp_paths import temp_path


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _matches(left: Any, right: Any) -> bool:
    a, b = _norm(left), _norm(right)
    return bool(a and b and (a == b or a in b or b in a))


def _mechanism_key(value: Any) -> str:
    aliases = {
        "aliasing": "aliasingeffect",
        "antenna": "antennaeffect",
        "nonidealcutoffeffect": "nonidealcutoff",
        "nonlinearityeffect": "nonlinearity",
        "photoelectroniceffect": "photoelectriceffect",
    }
    key = _norm(value)
    return aliases.get(key, key)


def _mechanism_matches(left: Any, right: Any) -> bool:
    a, b = _mechanism_key(left), _mechanism_key(right)
    return bool(a and b and a == b)


def _load_json(filename: str, default: Any) -> Any:
    path = temp_path(filename)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _verification_contexts(single_results: List[Dict[str, Any]]) -> Dict[tuple, str]:
    contexts: Dict[tuple, str] = {}
    for result in single_results or []:
        item = result.get("source_vulnerability_item") or {}
        key = (_norm(item.get("vulnerability_name")), _norm(item.get("mechanism_name")))
        conditions = []
        for plan in result.get("verification_plans") or []:
            if not isinstance(plan, dict):
                continue
            modality = plan.get("attack_signal_modality")
            frequency = plan.get("attack_freq_range")
            unit = plan.get("attack_freq_unit") or ""
            other = plan.get("attack_signal_parameter_range")
            if modality:
                conditions.append(f"modality={modality}")
            if frequency:
                if isinstance(frequency, (list, tuple)) and len(frequency) >= 2:
                    conditions.append(f"frequency={frequency[0]}-{frequency[1]} {unit}".strip())
                else:
                    conditions.append(f"frequency={frequency} {unit}".strip())
            if other:
                conditions.append(str(other))
        if conditions:
            contexts[key] = "Regression-test this mitigation under the Step 4 conditions: " + "; ".join(conditions)
    return contexts


def _matching_paths(item: Dict[str, Any], graph_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    paths = [
        path
        for path in (
            list(graph_data.get("accepted_paths", []) or [])
            + list(graph_data.get("unresolved_paths", []) or [])
        )
        if isinstance(path, dict)
    ]
    by_id = {str(path.get("path_id")): path for path in paths}
    return [
        by_id[path_id]
        for path_id in map(str, item.get("supporting_path_ids") or [])
        if path_id in by_id
    ]


def _node_label(node_id: Any, node_map: Dict[str, Dict[str, Any]]) -> str:
    node = node_map.get(str(node_id), {})
    return str(node.get("component_name") or node.get("name") or node_id or "unknown node")


def _critical_edge(item: Dict[str, Any], path: Dict[str, Any]) -> Dict[str, Any]:
    mechanism = item.get("mechanism_name")
    component = item.get("source_component")
    node_map = {str(node.get("node_id")): node for node in path.get("nodes", []) or [] if isinstance(node, dict)}
    ranked = []
    for index, edge in enumerate(path.get("edges", []) or []):
        if not isinstance(edge, dict):
            continue
        source = _node_label(edge.get("source_node_id"), node_map)
        target = _node_label(edge.get("target_node_id"), node_map)
        score = 0
        if _mechanism_matches(edge.get("mechanism_name"), mechanism):
            score += 100
        if _matches(source, component) or _matches(target, component):
            score += 30
        if str(edge.get("relation_type") or "").casefold() in {"couple", "apply", "amplify", "sample", "convert", "filter"}:
            score += 10
        ranked.append((score, -index, edge, source, target))
    matching = [entry for entry in ranked if entry[0] >= 100]
    if not matching:
        return {}
    _, _, edge, source, target = max(matching, key=lambda entry: (entry[0], entry[1]))
    return {
        "edge_id": edge.get("edge_id"),
        "source_node": source,
        "target_node": target,
        "relation_type": edge.get("relation_type"),
        "mechanism_name": edge.get("mechanism_name") or mechanism,
        "input_modality": edge.get("input_modality"),
        "output_modality": edge.get("output_modality"),
        "explanation": edge.get("explanation"),
    }


def _path_trace(path: Dict[str, Any]) -> str:
    node_map = {str(node.get("node_id")): node for node in path.get("nodes", []) or [] if isinstance(node, dict)}
    parts = []
    for edge in path.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue
        source = _node_label(edge.get("source_node_id"), node_map)
        target = _node_label(edge.get("target_node_id"), node_map)
        relation = str(edge.get("relation_type") or "propagate")
        mechanism = str(edge.get("mechanism_name") or "")
        label = f"{relation}: {mechanism}" if mechanism else relation
        parts.append(f"{source} --[{label}]--> {target}")
    return " ; ".join(parts)


def _edge_defense(edge: Dict[str, Any], item: Dict[str, Any]) -> str:
    mechanism = _mechanism_key(edge.get("mechanism_name") or item.get("mechanism_name"))
    relation = _norm(edge.get("relation_type"))
    target = str(edge.get("target_node") or item.get("source_component") or "target component")
    actions = {
        "antennaeffect": f"Reduce unintended coupling before {target} with shielding, grounding, shorter return paths, shielded or twisted wiring, and common-mode or low-pass filtering.",
        "saturationeffect": f"Prevent overdrive at {target} with input limiting or clamping, gain control, added headroom, and saturation detection.",
        "nonlinearity": f"Keep {target} in its linear region using amplitude limiting, linearized front-end design, differential routing, and distortion monitoring.",
        "nonidealcutoff": f"Strengthen attenuation at {target} with a higher-order or better-characterized filter and verify stop-band rejection across tolerances.",
        "aliasingeffect": f"Block this edge before sampling at {target} with an analog anti-alias filter, adequate sampling rate, clock integrity checks, and rejection of folded spectral components.",
        "resonanceeffect": f"Weaken resonant transfer into {target} with mechanical damping, isolation, detuning, or a notch filter around the verified resonance.",
        "photoacousticeffect": f"Interrupt optical-to-acoustic conversion at {target} using wavelength-selective blocking, opaque shielding, thermal damping, and acoustic isolation.",
        "photoelectriceffect": f"Suppress unintended optical conversion at {target} using spectral filters, opaque packaging, baffling, and saturation-aware optical validation.",
    }
    recommendation = actions.get(mechanism)
    if recommendation:
        return recommendation
    relation_actions = {
        "couple": f"Attenuate or isolate the coupling boundary between {edge.get('source_node')} and {target}.",
        "amplify": f"Limit gain and clamp abnormal amplitude before it propagates through {target}.",
        "sample": f"Add anti-alias filtering and sampling-integrity checks before {target}.",
        "propagate": f"Insert isolation, filtering, or plausibility validation at the interface into {target}.",
        "observe": f"Reject implausible output at {target} with consistency and temporal anomaly checks.",
    }
    return relation_actions.get(relation, f"Add an isolation or validation control at the edge entering {target}.")


def build_path_linked_defenses(
    vulnerability_items: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
    single_results: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    contexts = _verification_contexts(single_results or [])
    output = []
    for item in vulnerability_items or []:
        paths = _matching_paths(item, graph_data)
        if not paths:
            output.append({
                "vulnerability_name": item.get("vulnerability_name"),
                "mechanism_name": item.get("mechanism_name"),
                "source_component": item.get("source_component"),
                "traceability_status": "Step 3 supporting path ID is missing or unavailable",
            })
            continue
        for path in paths:
            edge = _critical_edge(item, path)
            if not edge:
                output.append({
                    "vulnerability_name": item.get("vulnerability_name"),
                    "mechanism_name": item.get("mechanism_name"),
                    "source_component": item.get("source_component"),
                    "path_id": path.get("path_id"),
                    "traceability_status": "supporting path has no matching mechanism edge",
                })
                continue
            mechanism = edge.get("mechanism_name") or item.get("mechanism_name")
            output.append({
                "vulnerability_name": item.get("vulnerability_name"),
                "mechanism_name": mechanism,
                "source_component": item.get("source_component"),
                "path_id": path.get("path_id"),
                "path_status": path.get("status"),
                "external_modality": (path.get("external_signal") or {}).get("modality"),
                "observable_output": path.get("observable_output"),
                "path_trace": _path_trace(path),
                "critical_edge": edge,
                "principle": edge.get("explanation") or item.get("judgment_reason") or item.get("description"),
                "recommendation": _edge_defense(edge, item),
                "verification_context": contexts.get((_norm(item.get("vulnerability_name")), _norm(item.get("mechanism_name"))), ""),
                "traceability_status": "Step 3 path and mechanism edge linked",
            })
    return output


def run_step_5():
    print("\n---------------------------------Step 5: Path-linked defense recommendations----------------------------------")
    vulnerability_items = _load_json("step3_vulnerability_items.json", [])
    graph_data = _load_json("step2_mechanism_paths.json", {})
    single_results = _load_json("step4_single_results.json", [])
    defense_items = build_path_linked_defenses(vulnerability_items, graph_data, single_results)
    temp_path("step5_defense_items.json").write_text(
        json.dumps(defense_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    defense_markdown = render_defense_recommendations(defense_items)
    temp_path("step5_output.txt").write_text(defense_markdown, encoding="utf-8")
    append_report(output_report, "\n" + defense_markdown)
    return defense_markdown
