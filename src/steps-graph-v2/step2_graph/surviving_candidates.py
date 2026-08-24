from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .constants import STATUS_FALSE, STATUS_TRUE, STATUS_UNKNOWN
from .sensor_parameters import parameters_for_path


def collect_surviving_path_mechanism_candidates(
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Collect mechanism edges only from paths that survived path adjudication.

    Rejected paths remain in the payload as an audit trail, but none of their
    edges may become a Step2 mechanism candidate.  This function works on the
    serialized payload so it can also repair completed runs without another LLM
    call.
    """
    ranked_status = {STATUS_UNKNOWN: 1, STATUS_TRUE: 2}
    candidates: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    surviving_paths: Iterable[Dict[str, Any]] = (
        list(payload.get("accepted_paths", []) or [])
        + list(payload.get("unresolved_paths", []) or [])
    )
    parameter_catalog = payload.get("sensor_parameter_catalog", []) or []

    for path in surviving_paths:
        path_id = str(path.get("path_id", ""))
        path_status = str(path.get("status", ""))
        nodes = {
            str(node.get("node_id", "")): node
            for node in path.get("nodes", []) or []
            if isinstance(node, dict)
        }
        for edge in path.get("edges", []) or []:
            if not isinstance(edge, dict):
                continue
            mechanism_name = edge.get("mechanism_name")
            status = edge.get("final_status", STATUS_UNKNOWN)
            if not mechanism_name or status == STATUS_FALSE:
                continue

            source = nodes.get(str(edge.get("source_node_id", "")), {})
            target = nodes.get(str(edge.get("target_node_id", "")), {})
            component = (
                target.get("component_name")
                or target.get("name")
                or source.get("component_name")
                or source.get("name")
                or ""
            )
            component_categories = {
                str(node.get("component_category", ""))
                for node in (source, target)
                if node.get("component_category")
            }
            attack_origin = str(edge.get("attack_origin", ""))
            relevant_parameters = parameters_for_path(
                parameter_catalog,
                component_categories,
                attack_origin,
            )
            item = {
                "mechanism_name": mechanism_name,
                "source_component": component,
                "status": status,
                "edge_id": edge.get("edge_id", ""),
                "attack_origin": attack_origin,
                "input_modality": edge.get("input_modality", ""),
                "output_modality": edge.get("output_modality", ""),
                "plain_language_analysis": edge.get("explanation", ""),
                "mandatory_preconditions": list(
                    edge.get("mandatory_preconditions", []) or []
                ),
                "parameter_constraints": list(
                    edge.get("parameter_constraints", []) or []
                ),
                "evidence_refs": list(edge.get("supporting_evidence", []) or []),
                "relevant_parameter_refs": [
                    str(parameter.get("parameter_id"))
                    for parameter in relevant_parameters
                ],
                "relevant_sensor_parameters": relevant_parameters,
                "requires_followup_verification": status == STATUS_UNKNOWN,
                "supporting_path_ids": [path_id] if path_id else [],
                "supporting_path_statuses": [path_status] if path_status else [],
            }
            key = (mechanism_name, str(component).strip().lower(), attack_origin)
            previous = candidates.get(key)
            if previous is None:
                candidates[key] = item
                continue

            previous["supporting_path_ids"] = sorted(
                set(previous.get("supporting_path_ids", []))
                | set(item["supporting_path_ids"])
            )
            previous["supporting_path_statuses"] = sorted(
                set(previous.get("supporting_path_statuses", []))
                | set(item["supporting_path_statuses"])
            )
            if ranked_status.get(status, 0) > ranked_status.get(
                previous.get("status", ""), 0
            ):
                item["supporting_path_ids"] = previous["supporting_path_ids"]
                item["supporting_path_statuses"] = previous[
                    "supporting_path_statuses"
                ]
                candidates[key] = item

    return sorted(
        candidates.values(),
        key=lambda item: (
            item["mechanism_name"],
            str(item["source_component"]).lower(),
            item["attack_origin"],
        ),
    )


def filter_existing_candidates_to_surviving_paths(
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Delete unsupported historical candidates without introducing new ones."""
    surviving = collect_surviving_path_mechanism_candidates(payload)
    surviving_edge_ids = {
        str(item.get("edge_id", "")) for item in surviving if item.get("edge_id")
    }
    surviving_keys = {
        (
            str(item.get("mechanism_name", "")),
            str(item.get("source_component", "")).strip().lower(),
            str(item.get("attack_origin", "")),
        )
        for item in surviving
    }
    result: List[Dict[str, Any]] = []
    for candidate in payload.get("mechanism_candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        edge_id = str(candidate.get("edge_id", ""))
        key = (
            str(candidate.get("mechanism_name", "")),
            str(candidate.get("source_component", "")).strip().lower(),
            str(candidate.get("attack_origin", "")),
        )
        if edge_id in surviving_edge_ids or key in surviving_keys:
            result.append(candidate)
    return result
