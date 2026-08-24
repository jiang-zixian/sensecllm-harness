from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from helpers.api.chatanywhere_client import chatanywhere_chat_completion
from helpers.configs.configs import chatanywhere_auth_header

from .component_ontology import TRANSDUCER_CATEGORIES
from .constants import ALLOWED_MECHANISMS, NORMAL_RELATIONS
from .models import GraphNode, SearchState, SensorPhysicalGraph
from .operator_registry import PhysicalOperatorRegistry
from .prompts import build_candidate_expansion_prompts
from .serialization import dumps_compact, extract_json_payload


def _coerce_chat_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts)
    return str(content)


def _extract_chat_content(response_data: Dict[str, Any]) -> str:
    try:
        message = response_data["choices"][0]["message"]
    except Exception as exc:
        raise RuntimeError(f"ChatAnywhere response format error: {exc}; response={response_data}") from exc
    if not isinstance(message, dict):
        raise RuntimeError(f"ChatAnywhere message is not an object: {message}")
    for key in ("content", "reasoning_content", "reasoning", "refusal"):
        text = _coerce_chat_content(message.get(key))
        if text.strip():
            return text
    raise RuntimeError(f"ChatAnywhere response contains no text; response={response_data}")


def _repair_candidate_json(raw: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    response = chatanywhere_chat_completion(
        model="gpt-5.4-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    system_prompt
                    + "\n\n"
                    "Convert the supplied model reasoning into strict JSON only. "
                    "Preserve only candidate expansions supported by that reasoning. "
                    "Follow every candidate-object field and schema requirement above. "
                    "Return exactly one object with a candidate_expansions array; do not explain."
                ),
            },
            {
                "role": "user",
                "content": (
                    user_prompt
                    + "\n\nThe core model produced the following reasoning without a valid final JSON. "
                    "Convert it to the exact required schema without adding unsupported claims:\n"
                    + raw
                ),
            },
        ],
        auth_header=chatanywhere_auth_header,
        temperature=0.0,
        timeout=300,
        max_tokens=6000,
    )
    return extract_json_payload(_extract_chat_content(response))


def _component_by_category(graph: SensorPhysicalGraph, *categories: str) -> List[GraphNode]:
    wanted = set(categories)
    return [node for node in graph.component_nodes() if node.component_category in wanted]


def _first_component(graph: SensorPhysicalGraph, *categories: str) -> Optional[GraphNode]:
    matches = _component_by_category(graph, *categories)
    return matches[0] if matches else None


def _first_conductor(graph: SensorPhysicalGraph) -> Optional[GraphNode]:
    for node in graph.boundary_nodes() + graph.component_nodes():
        text = f"{node.name} {node.component_name}".lower()
        if node.component_category in {"Wires", "Power Supply", "Communication Interface"} or any(k in text for k in ["pin", "trace", "pcb", "wire", "cable", "line"]):
            return node
    return None


def _first_inferred_optical_access(graph: SensorPhysicalGraph) -> Optional[GraphNode]:
    for node in graph.boundary_nodes():
        if node.modality == "optical" and "optical access" in node.name.lower():
            return node
    return None


def _first_photosensitive_microphone_structure(graph: SensorPhysicalGraph) -> Optional[GraphNode]:
    for node in graph.component_nodes():
        text = f"{node.name} {node.component_name}".lower()
        if "photosensitive" in text or "junction" in text:
            return node
    return None


def _is_microphone_graph(graph: SensorPhysicalGraph) -> bool:
    text = " ".join(
        [graph.sensor_model]
        + [node.name for node in graph.component_nodes()]
        + [node.component_name for node in graph.component_nodes()]
    ).lower()
    return any(keyword in text for keyword in ["microphone", "i2s", "i²s"])


def _candidate(
    source_node_id: str,
    target: Dict[str, Any],
    relation_type: str,
    mechanism_name: Optional[str] = None,
    explanation: str = "",
    **flags: Any,
) -> Dict[str, Any]:
    result = {
        "source_node_id": source_node_id,
        "proposed_target": {
            "node_type": target.get("node_type", "SignalStateNode"),
            "name": target.get("name", ""),
            "modality": target.get("modality", ""),
            "component_category": target.get("component_category", ""),
            "component_name": target.get("component_name", ""),
        },
        "relation_type": relation_type,
        "mechanism_name": mechanism_name,
        "mandatory_preconditions": target.get("mandatory_preconditions", []),
        "parameter_constraints": target.get("parameter_constraints", []),
        "unknown_preconditions": target.get("unknown_preconditions", []),
        "retrieval_queries": target.get("retrieval_queries", []),
        "plain_language_explanation": explanation,
    }
    result.update(flags)
    return result


def _merge_candidate_sets(*candidate_sets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for candidates in candidate_sets:
        for candidate in candidates:
            target = candidate.get("proposed_target") or {}
            key = (
                candidate.get("source_node_id"),
                target.get("node_type"),
                str(target.get("name") or "").strip().lower(),
                str(target.get("component_name") or "").strip().lower(),
                candidate.get("relation_type"),
                candidate.get("mechanism_name"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(candidate)
    return merged


def _compact_graph_for_prompt(graph: SensorPhysicalGraph) -> Dict[str, Any]:
    return {
        "sensor_model": graph.sensor_model,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "name": node.name,
                "modality": node.modality,
                "component_category": node.component_category,
                "component_name": node.component_name,
                "evidence_status": node.evidence_status,
                "source_stage": node.source_stage,
            }
            for node in graph.nodes.values()
        ],
        "structural_edges": [
            {
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "relation_type": edge.relation_type,
                "mechanism_name": edge.mechanism_name,
                "final_status": edge.final_status,
            }
            for edge in graph.edges.values()
        ],
        "evidence_catalog": [
            {
                "evidence_id": evidence.evidence_id,
                "source_type": evidence.source_type,
                "source_name": evidence.source_name,
                "supports_claim": evidence.supports_claim,
                "evidence_scope": evidence.evidence_scope,
                "reliability_level": evidence.reliability_level,
            }
            for evidence in graph.evidence.values()
        ],
    }


def _compact_operator_context(expansion_task: str = "") -> Dict[str, Any]:
    if expansion_task == "entry_expansion":
        return {
            "normal_relations": ["block", "couple", "reach"],
            "allowed_mechanisms": [],
        }
    if expansion_task == "signal_propagation_expansion":
        return {
            "normal_relations": ["propagate", "filter", "sample", "observe", "block"],
            "allowed_mechanisms": list(ALLOWED_MECHANISMS),
        }
    if expansion_task == "structure_completion_expansion":
        return {
            "normal_relations": ["reach", "propagate", "couple"],
            "allowed_mechanisms": [],
        }
    if expansion_task == "mixed_layer_expansion":
        return {
            "normal_relations": sorted(NORMAL_RELATIONS),
            "allowed_mechanisms": list(ALLOWED_MECHANISMS),
            "note": "Each frontier state carries its own expansion_task; apply the matching local rules.",
        }
    return {
        "normal_relations": sorted(NORMAL_RELATIONS),
        "allowed_mechanisms": list(ALLOWED_MECHANISMS),
    }


def _trim_text(value: str, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated for local graph-search prompt]..."


def _architecture_order(node: GraphNode) -> int:
    order = {
        "Acoustic Transducer": 10,
        "Optical Transducer": 10,
        "Electromagnetic Transducer": 10,
        "Force Transducer": 10,
        "Amplifier": 20,
        "Filter": 30,
        "ADC": 40,
        "DSP": 50,
        "Communication Interface": 60,
        "Wires": 80,
        "Power Supply": 90,
        "Clock Oscillator": 95,
    }
    return order.get(node.component_category, 100)


def _node_ref(node: GraphNode) -> Dict[str, Any]:
    return {
        "node_id": node.node_id,
        "node_type": node.node_type,
        "name": node.name,
        "modality": node.modality,
        "component_category": node.component_category,
        "component_name": node.component_name,
        "architecture_order": _architecture_order(node) if node.node_type in {"ComponentNode", "BoundaryNode"} else None,
        "evidence_status": node.evidence_status,
        "source_stage": node.source_stage,
    }


def _edge_ref(edge: Any) -> Dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relation_type": edge.relation_type,
        "mechanism_name": edge.mechanism_name,
        "final_status": edge.final_status,
    }


def _expansion_task_for_state(state: SearchState, graph: SensorPhysicalGraph) -> str:
    node = graph.nodes.get(state.current_node_id)
    if node is None:
        return "structure_completion_expansion"
    if node.node_type == "ExternalSignalNode":
        return "entry_expansion"
    if node.node_type in {"ComponentNode", "BoundaryNode"}:
        return "component_mechanism_expansion"
    if node.node_type == "SignalStateNode":
        return "signal_propagation_expansion"
    return "signal_propagation_expansion"


def _max_states_for_task(expansion_task: str, configured_limit: int) -> int:
    task_limits = {
        "component_mechanism_expansion": 3,
        "signal_propagation_expansion": 4,
        "structure_completion_expansion": 2,
    }
    return max(1, min(configured_limit, task_limits.get(expansion_task, configured_limit)))


def _compact_state_for_prompt(state: SearchState) -> Dict[str, Any]:
    return {
        "signal_origin": state.signal_origin,
        "current_node_id": state.current_node_id,
        "recent_visited_node_ids": state.visited_node_ids[-4:],
        "visited_node_count": len(state.visited_node_ids),
        "path_edge_count": len(state.path_edge_ids),
        "mechanisms_already_in_path": [
            {
                "mechanism_name": item.mechanism_name,
                "source_component": item.source_component,
            }
            for item in state.mechanism_instances
        ],
        "unknown_precondition_count": len(state.unknown_preconditions),
        "false_precondition_count": len(state.false_preconditions),
        "depth": state.depth,
    }


def _compact_local_graph_context(
    graph: SensorPhysicalGraph,
    state_batch: List[Tuple[str, SearchState]],
    expansion_task: str,
) -> Dict[str, Any]:
    current_ids = {state.current_node_id for _state_id, state in state_batch}
    visited_ids = {
        node_id
        for _state_id, state in state_batch
        for node_id in state.visited_node_ids
    }
    edge_ids = set()
    neighbor_ids = set(current_ids) | visited_ids
    for edge in graph.edges.values():
        if edge.source_node_id in current_ids or edge.target_node_id in current_ids:
            edge_ids.add(edge.edge_id)
            neighbor_ids.add(edge.source_node_id)
            neighbor_ids.add(edge.target_node_id)
        if edge.edge_id.startswith("structure_") and (
            edge.source_node_id in visited_ids or edge.target_node_id in visited_ids
        ):
            edge_ids.add(edge.edge_id)
            neighbor_ids.add(edge.source_node_id)
            neighbor_ids.add(edge.target_node_id)

    component_catalog = [
        _node_ref(node)
        for node in sorted(
            graph.component_nodes() + graph.boundary_nodes(),
            key=lambda item: (_architecture_order(item), item.node_id),
        )
    ]
    fixed_architecture_edges = [
        _edge_ref(edge)
        for edge in sorted(graph.edges.values(), key=lambda item: item.edge_id)
        if not edge.mechanism_name and graph.nodes.get(edge.source_node_id, None)
        and graph.nodes.get(edge.target_node_id, None)
        and graph.nodes[edge.source_node_id].node_type in {"ComponentNode", "BoundaryNode"}
        and graph.nodes[edge.target_node_id].node_type in {"ComponentNode", "BoundaryNode"}
    ]
    current_nodes = [
        _node_ref(graph.nodes[node_id])
        for node_id in sorted(current_ids)
        if node_id in graph.nodes
    ]
    neighborhood_nodes = [
        _node_ref(graph.nodes[node_id])
        for node_id in sorted(neighbor_ids)
        if node_id in graph.nodes and node_id not in current_ids
    ]
    structural_edges = [
        _edge_ref(graph.edges[edge_id])
        for edge_id in sorted(edge_ids)
        if edge_id in graph.edges
    ]
    path_summaries = []
    for state_id, state in state_batch:
        path_summaries.append(
            {
                "frontier_id": state_id,
                "signal_origin": state.signal_origin,
                "current_node_id": state.current_node_id,
                "visited_node_count": len(state.visited_node_ids),
                "recent_visited_node_ids": state.visited_node_ids[-4:],
                "path_edge_count": len(state.path_edge_ids),
                "mechanisms_already_in_path": [
                    {
                        "mechanism_name": item.mechanism_name,
                        "source_component": item.source_component,
                    }
                    for item in state.mechanism_instances
                ],
                "unknown_precondition_count": len(state.unknown_preconditions),
            }
        )
    return {
        "sensor_model": graph.sensor_model,
        "expansion_task": expansion_task,
        "current_nodes": current_nodes,
        "path_summaries": path_summaries,
        "component_and_boundary_catalog": component_catalog,
        "fixed_ordered_architecture_edges": fixed_architecture_edges,
        "nearby_nodes": neighborhood_nodes,
        "nearby_structural_edges": structural_edges,
    }


def _component_target(node: GraphNode, modality: Optional[str] = None) -> Dict[str, Any]:
    return {
        "node_type": node.node_type,
        "name": node.name,
        "modality": modality if modality is not None else node.modality,
        "component_category": node.component_category,
        "component_name": node.component_name or node.name,
    }


def _signal_target(
    name: str,
    modality: str,
    component: GraphNode,
    component_category: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "node_type": "SignalStateNode",
        "name": name,
        "modality": modality,
        "component_category": component_category or component.component_category,
        "component_name": component.component_name or component.name,
    }


def _components_accepting_origin(graph: SensorPhysicalGraph, origin: str) -> List[GraphNode]:
    categories = {
        "acoustic": {"Acoustic Transducer", "Force Transducer"},
        "optical": {"Optical Transducer"},
        "electromagnetic": {"Wires", "Power Supply", "Communication Interface"},
    }.get(origin, set())
    nodes = graph.component_nodes() + graph.boundary_nodes()
    matching = [node for node in nodes if node.component_category in categories]
    source_priority = {"step1": 0, "expert_knowledge": 1, "llm_inferred": 2}
    return sorted(
        matching,
        key=lambda node: (
            source_priority.get(node.source_stage, 3),
            node.component_category,
            (node.component_name or node.name).lower(),
        ),
    )


def _structural_successors(graph: SensorPhysicalGraph, component: GraphNode) -> List[GraphNode]:
    result = []
    for edge in graph.outgoing(component.node_id):
        if edge.mechanism_name or edge.target_node_id not in graph.nodes:
            continue
        target = graph.nodes[edge.target_node_id]
        if target.node_type == "ComponentNode":
            result.append(target)
    return result


def _source_components_for_signal(graph: SensorPhysicalGraph, signal: GraphNode) -> List[GraphNode]:
    name = (signal.component_name or "").strip().lower()
    if not name:
        return []
    return [
        node
        for node in graph.component_nodes() + graph.boundary_nodes()
        if (node.component_name or node.name).strip().lower() == name
    ]


def _generic_operator_candidates(state: SearchState, graph: SensorPhysicalGraph) -> List[Dict[str, Any]]:
    current = graph.nodes[state.current_node_id]
    candidates: List[Dict[str, Any]] = []

    if current.node_type == "ExternalSignalNode":
        for component in _components_accepting_origin(graph, state.signal_origin):
            candidates.append(
                _candidate(
                    current.node_id,
                    _component_target(component, state.signal_origin),
                    "reach",
                    explanation=(
                        f"The component ontology admits {state.signal_origin} energy at "
                        f"{component.component_name or component.name}."
                    ),
                )
            )
        return candidates

    if current.node_type in {"ComponentNode", "BoundaryNode"}:
        category = current.component_category
        origin = state.signal_origin

        for successor in _structural_successors(graph, current):
            candidates.append(
                _candidate(
                    current.node_id,
                    _component_target(successor, successor.modality or "electrical"),
                    "sample" if successor.component_category == "ADC" else "propagate",
                    explanation="Traverse an existing component-ontology processing-chain edge.",
                    high_frequency_input=origin in {"acoustic", "electromagnetic"},
                )
            )

        if category in TRANSDUCER_CATEGORIES:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("transduced electrical signal", "electrical", current),
                    "convert",
                    explanation="The transducer performs its normal physical-to-electrical conversion.",
                )
            )
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("finite-range transducer output", "electrical", current),
                    "apply",
                    "Saturation Effect",
                    explanation="Every physical transducer has a finite input/output dynamic range.",
                )
            )

        if origin == "acoustic" and category in {"Acoustic Transducer", "Force Transducer"}:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("mechanically resonant response", "mechanical", current),
                    "apply",
                    "Resonance Effect",
                    input_modality="acoustic",
                    explanation="Acoustic excitation can couple to a mechanically compliant sensing structure near resonance.",
                )
            )
        if origin == "acoustic" and category == "Acoustic Transducer":
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("out-of-band transducer response", "electrical", current),
                    "apply",
                    "Non-ideal Cutoff",
                    input_modality="acoustic",
                    explanation="A real acoustic transducer has a finite transition band rather than an ideal brick-wall cutoff.",
                )
            )
        if origin == "optical" and category == "Optical Transducer":
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("photo-generated electrical signal", "electrical", current),
                    "apply",
                    "Photoelectric Effect",
                    input_modality="optical",
                    explanation="A photosensitive transducer converts incident photons into electrical carriers.",
                )
            )
        if origin == "optical" and category in {"Acoustic Transducer", "Force Transducer"}:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("photoacoustically induced response", "electrical", current),
                    "apply",
                    "Photoacoustic Effect",
                    input_modality="optical",
                    explanation="Absorbed optical energy may create thermal expansion and mechanical response.",
                )
            )
        if origin == "electromagnetic" and category in {"Wires", "Power Supply", "Communication Interface"}:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("induced electrical interference", "electrical", current),
                    "apply",
                    "Antenna Effect",
                    input_modality="electromagnetic",
                    explanation="Conductive interconnects can pick up electromagnetic energy as induced voltage/current.",
                )
            )

        if category in {"Amplifier", "Signal Conditioning Circuits"}:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("finite-range conditioned signal", "electrical", current),
                    "apply",
                    "Saturation Effect",
                    explanation="Signal-conditioning circuits have finite voltage/current/output range.",
                )
            )
            if origin == "acoustic":
                candidates.append(
                    _candidate(
                        current.node_id,
                        _signal_target("nonlinearly converted analog signal", "electrical", current),
                        "apply",
                        "Nonlinearity",
                        explanation="A nonlinear analog transfer can rectify, mix, or demodulate acoustic-origin interference.",
                    )
                )
        if category == "Filter" and origin == "acoustic":
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("leaked stop-band signal", "electrical", current),
                    "apply",
                    "Non-ideal Cutoff",
                    explanation="A real filter has finite attenuation and a nonzero transition/stop-band response.",
                )
            )
        if category == "ADC" and origin in {"acoustic", "electromagnetic"}:
            candidates.append(
                _candidate(
                    current.node_id,
                    _signal_target("aliased digital component", "digital", current),
                    "apply",
                    "Aliasing Effect",
                    high_frequency_input=True,
                    explanation="Sampling can fold a high-frequency component into the represented digital band.",
                )
            )
        return candidates

    if current.node_type == "SignalStateNode":
        downstream: List[GraphNode] = []
        for source_component in _source_components_for_signal(graph, current):
            downstream.extend(_structural_successors(graph, source_component))
        if current.modality == "electrical" and (
            "induced" in current.name.lower() or not downstream
        ):
            downstream.extend(
                node
                for node in graph.component_nodes()
                if node.component_category
                in {"Amplifier", "Signal Conditioning Circuits", "Filter", "ADC", "DSP", "Communication Interface"}
            )
        seen = set()
        for target in downstream:
            if target.node_id in seen or target.node_id in state.visited_node_ids:
                continue
            seen.add(target.node_id)
            candidates.append(
                _candidate(
                    current.node_id,
                    _component_target(target, target.modality or "electrical"),
                    "sample" if target.component_category == "ADC" else "propagate",
                    explanation="Propagate the signal along an existing or ontology-completed processing stage.",
                    high_frequency_input=state.signal_origin in {"acoustic", "electromagnetic"},
                )
            )
        if "induced" in current.name.lower():
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "electrically overdriven interface signal",
                        "modality": "electrical",
                        "component_category": "Signal Conditioning Circuits",
                        "component_name": current.component_name,
                    },
                    "apply",
                    "Saturation Effect",
                    assume_qualitative_overdrive=True,
                    explanation="Induced voltage/current can exceed the finite range of an input, output, clamp, or conditioning circuit.",
                )
            )
        if state.mechanism_instances:
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "ObservableOutputNode",
                        "name": _observable_name(graph),
                        "modality": "digital" if current.modality == "digital" else "electrical",
                        "component_category": current.component_category,
                        "component_name": current.component_name,
                    },
                    "observe",
                    explanation="A mechanism-bearing signal is a Step2-relevant abnormal sensor output candidate.",
                )
            )
    return candidates


class LocalCandidateExpansionGenerator:
    uses_structural_closure = False

    def generate_layer(
        self,
        state_batch: List[Tuple[str, SearchState]],
        graph: SensorPhysicalGraph,
        registry: PhysicalOperatorRegistry,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            state_id: self.generate(state, graph, registry)
            for state_id, state in state_batch
        }

    def generate(self, state: SearchState, graph: SensorPhysicalGraph, registry: PhysicalOperatorRegistry) -> List[Dict[str, Any]]:
        return _merge_candidate_sets(
            _generic_operator_candidates(state, graph),
            self._generate_legacy(state, graph, registry),
        )

    def _generate_legacy(self, state: SearchState, graph: SensorPhysicalGraph, registry: PhysicalOperatorRegistry) -> List[Dict[str, Any]]:
        current = graph.nodes[state.current_node_id]
        name = current.name.lower()
        category = current.component_category
        candidates: List[Dict[str, Any]] = []

        if current.node_type == "ExternalSignalNode":
            if state.signal_origin == "electromagnetic":
                conductor = _first_conductor(graph)
                if conductor:
                    candidates.append(
                        _candidate(
                            current.node_id,
                            {
                                "node_type": conductor.node_type,
                                "name": conductor.name,
                                "modality": "electromagnetic",
                                "component_category": conductor.component_category,
                                "component_name": conductor.component_name or conductor.name,
                            },
                            "reach",
                            explanation="External electromagnetic energy reaches an explicitly listed conductive structure.",
                        )
                    )
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "mechanical vibration",
                            "modality": "mechanical",
                            "component_category": "",
                            "component_name": "",
                        },
                        "apply",
                        "Resonance Effect",
                        explanation="Deliberately test and reject direct EM-to-resonance expansion.",
                    )
                )
            elif state.signal_origin == "optical":
                optical = _first_component(graph, "Optical Transducer")
                if optical:
                    candidates.append(
                        _candidate(
                            current.node_id,
                            {
                                "node_type": "ComponentNode",
                                "name": optical.name,
                                "modality": "optical",
                                "component_category": optical.component_category,
                                "component_name": optical.component_name or optical.name,
                            },
                            "reach",
                            explanation="External optical signal reaches the optical transducer listed in Step1.",
                        )
                    )
                optical_access = _first_inferred_optical_access(graph)
                if optical_access:
                    candidates.append(
                        _candidate(
                            current.node_id,
                            {
                                "node_type": "BoundaryNode",
                                "name": optical_access.name,
                                "modality": "optical",
                                "component_category": optical_access.component_category,
                                "component_name": optical_access.component_name or optical_access.name,
                            },
                            "reach",
                            explanation="External optical energy reaches the inferred microphone optical access unless Step1 states optical shielding.",
                        )
                    )
            elif state.signal_origin == "acoustic":
                acoustic = _first_component(graph, "Acoustic Transducer", "Force Transducer")
                if acoustic:
                    candidates.append(
                        _candidate(
                            current.node_id,
                            {
                                "node_type": "ComponentNode",
                                "name": acoustic.name,
                                "modality": "acoustic",
                                "component_category": acoustic.component_category,
                                "component_name": acoustic.component_name or acoustic.name,
                            },
                            "reach",
                            explanation="External acoustic signal reaches an acoustic or mechanical transducer listed in Step1.",
                        )
                    )
            return candidates

        if current.node_type in {"BoundaryNode", "ComponentNode"} and state.signal_origin == "electromagnetic":
            text = f"{current.name} {current.component_name}".lower()
            if current.component_category in {"Wires", "Power Supply", "Communication Interface"} or any(k in text for k in ["pin", "trace", "pcb", "wire", "cable", "line"]):
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "induced electrical interference",
                            "modality": "electrical",
                            "component_category": current.component_category,
                            "component_name": current.component_name or current.name,
                        },
                        "apply",
                        "Antenna Effect",
                        explanation="The conductive structure can behave as an unintended antenna and induce voltage or current.",
                        input_modality="electromagnetic",
                    )
                )

        if current.node_type == "BoundaryNode" and state.signal_origin == "optical" and "optical access" in current.name.lower():
            acoustic = _first_component(graph, "Acoustic Transducer", "Force Transducer")
            photosensitive = _first_photosensitive_microphone_structure(graph)
            if acoustic:
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "photoacoustically induced distorted microphone signal",
                            "modality": "electrical",
                            "component_category": acoustic.component_category,
                            "component_name": acoustic.component_name or acoustic.name,
                        },
                        "apply",
                        "Photoacoustic Effect",
                        explanation="Optical absorption near the microphone port or MEMS structure can create thermal expansion or acoustic pressure that the microphone converts into a distorted electrical/audio signal.",
                        input_modality="optical",
                        assume_microphone_photoacoustic_prior=True,
                    )
                )
            if photosensitive:
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "photoelectrically induced DC bias",
                            "modality": "electrical",
                            "component_category": photosensitive.component_category,
                            "component_name": photosensitive.component_name or photosensitive.name,
                        },
                        "apply",
                        "Photoelectric Effect",
                        explanation="Optical illumination can generate carriers in inferred photosensitive MEMS/ASIC junctions and introduce current, voltage, or DC bias into the microphone electronics.",
                        input_modality="optical",
                        assume_microphone_photoelectric_prior=True,
                    )
                )

        if current.node_type == "ComponentNode" and state.signal_origin == "optical" and current.component_category == "Optical Transducer":
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "clipped electrical charge output",
                        "modality": "electrical",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Saturation Effect",
                    explanation="High optical intensity can exceed charge/full-well capacity and clip the electrical output.",
                    assume_qualitative_overdrive=True,
                )
            )
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "photo-generated current",
                        "modality": "electrical",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Photoelectric Effect",
                    explanation="Optical input can generate charge or current in a photosensitive transducer.",
                )
            )

        if current.node_type == "ComponentNode" and state.signal_origin == "acoustic" and current.component_category in {"Acoustic Transducer", "Force Transducer"}:
            if _is_microphone_graph(graph):
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "modulated ultrasonic electrical transducer signal",
                            "modality": "electrical",
                            "component_category": current.component_category,
                            "component_name": current.component_name or current.name,
                        },
                        "convert",
                        explanation=(
                            "A microphone transducer converts incident pressure to an electrical signal. "
                            "For DolphinAttack-style analysis, a modulated ultrasonic component must be "
                            "propagated to the analog front-end rather than discarded at candidate generation."
                        ),
                        high_frequency_input=True,
                        modulated_high_frequency_input=True,
                    )
                )
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "leaked out-of-band electrical microphone signal",
                            "modality": "electrical",
                            "component_category": current.component_category,
                            "component_name": current.component_name or current.name,
                            "mandatory_preconditions": [
                                {
                                    "claim": "The acoustic input lies above the microphone's intended passband.",
                                    "required_evidence_scope": "target_specific",
                                    "current_status": "TRUE",
                                    "evidence_refs": list(current.evidence_refs),
                                },
                                {
                                    "claim": "The transition/stop band has nonzero response, so some out-of-band energy propagates.",
                                    "required_evidence_scope": "generic_physics",
                                    "current_status": "TRUE",
                                    "evidence_refs": list(current.evidence_refs),
                                },
                            ],
                        },
                        "apply",
                        "Non-ideal Cutoff",
                        explanation=(
                            "A real microphone/transducer and its filters do not have a brick-wall cutoff. "
                            "Ultrasonic energy near the documented band edge can therefore leak into the "
                            "electrical signal path."
                        ),
                        input_modality="acoustic",
                        out_of_band_input=True,
                        nonzero_stopband_response=True,
                    )
                )
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "clipped or biased electrical microphone signal",
                        "modality": "electrical",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Saturation Effect",
                    explanation="A sufficiently large acoustic pressure can exceed the transducer or front-end dynamic range and bias or clip the electrical signal.",
                    assume_qualitative_overdrive=True,
                )
            )
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "mechanical vibration",
                        "modality": "mechanical",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Resonance Effect",
                    explanation="Acoustic energy may excite a microphone mechanical structure, but resonant frequency evidence is target-specific.",
                    input_modality="acoustic",
                )
            )

        if current.node_type == "SignalStateNode" and current.modality == "electrical":
            afe = _first_component(graph, "Amplifier", "Signal Conditioning Circuits")
            adc = _first_component(graph, "ADC")
            dsp = _first_component(graph, "DSP", "Communication Interface")
            carries_high_frequency = any(
                keyword in name
                for keyword in ["induced", "ultrasonic", "out-of-band", "high-frequency"]
            )
            if carries_high_frequency and afe:
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "ComponentNode",
                            "name": afe.name,
                            "modality": "electrical",
                            "component_category": afe.component_category,
                            "component_name": afe.component_name or afe.name,
                        },
                        "propagate",
                        explanation="The electrical interference or out-of-band transducer signal propagates into the analog front-end listed in Step1.",
                        high_frequency_input=True,
                        modulated_high_frequency_input="modulated" in name,
                    )
                )
            if carries_high_frequency and adc:
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "ComponentNode",
                            "name": adc.name,
                            "modality": "electrical",
                            "component_category": adc.component_category,
                            "component_name": adc.component_name or adc.name,
                        },
                        "sample",
                        explanation="High-frequency electrical interference reaches the ADC sampling input.",
                        high_frequency_input=True,
                    )
                )
            if "induced" in name and any(k in (graph.sensor_model + " " + " ".join(n.name for n in graph.component_nodes())).lower() for k in ["ccd", "camera", "video"]):
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "ObservableOutputNode",
                            "name": "distorted electrical video output",
                            "modality": "digital",
                            "component_category": current.component_category,
                            "component_name": current.component_name,
                        },
                        "observe",
                        explanation="The induced electrical interference can be observed as distorted electrical video output.",
                    )
                )
            if any(
                k in name
                for k in [
                    "clipped",
                    "biased",
                    "bias",
                    "distorted",
                    "saturated",
                    "demodulated",
                    "out-of-band",
                    "photoacoustic",
                    "photoelectric",
                ]
            ) and (adc or dsp):
                target = adc or dsp
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "ObservableOutputNode",
                            "name": _observable_name(graph),
                            "modality": "digital",
                            "component_category": target.component_category,
                            "component_name": target.component_name or target.name,
                        },
                        "observe",
                        explanation="The distorted electrical signal is observable as an abnormal sensor output.",
                    )
                )

        if current.node_type == "ComponentNode" and current.component_category == "Amplifier":
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "clipped or biased analog signal",
                        "modality": "electrical",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Saturation Effect",
                    explanation="The analog front-end can saturate and produce clipped or biased analog output.",
                    assume_qualitative_overdrive=True,
                )
            )
            if state.signal_origin == "acoustic" and _is_microphone_graph(graph):
                candidates.append(
                    _candidate(
                        current.node_id,
                        {
                            "node_type": "SignalStateNode",
                            "name": "demodulated in-band analog microphone signal",
                            "modality": "electrical",
                            "component_category": current.component_category,
                            "component_name": current.component_name or current.name,
                            "mandatory_preconditions": [
                                {
                                    "claim": "The acoustic carrier is amplitude modulated and reaches the microphone analog front-end.",
                                    "required_evidence_scope": "generic_physics",
                                    "current_status": "TRUE",
                                    "evidence_refs": list(current.evidence_refs),
                                },
                                {
                                    "claim": "A nonlinear transfer term produces a baseband component from the modulated ultrasonic carrier.",
                                    "required_evidence_scope": "generic_physics",
                                    "current_status": "TRUE",
                                    "evidence_refs": list(current.evidence_refs),
                                },
                            ],
                        },
                        "apply",
                        "Nonlinearity",
                        explanation=(
                            "DolphinAttack-style modulated ultrasound can be demodulated by nonlinear "
                            "MEMS/analog-front-end transfer terms, creating an in-band signal that survives "
                            "later low-pass filtering."
                        ),
                        input_modality="electrical",
                        modulated_high_frequency_input=True,
                        assume_microphone_ultrasonic_nonlinearity_prior=True,
                    )
                )

        if current.node_type == "ComponentNode" and current.component_category == "ADC":
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "SignalStateNode",
                        "name": "aliased digital component",
                        "modality": "digital",
                        "component_category": current.component_category,
                        "component_name": current.component_name or current.name,
                    },
                    "apply",
                    "Aliasing Effect",
                    explanation="ADC sampling can fold high-frequency input into an aliased digital component.",
                    high_frequency_input=True,
                )
            )

        if current.node_type == "SignalStateNode" and current.modality == "digital":
            candidates.append(
                _candidate(
                    current.node_id,
                    {
                        "node_type": "ObservableOutputNode",
                        "name": _observable_name(graph),
                        "modality": "digital",
                        "component_category": current.component_category,
                        "component_name": current.component_name,
                    },
                    "observe",
                    explanation="The aliased digital component appears as an abnormal sensor reading.",
                )
            )

        return candidates


def _observable_name(graph: SensorPhysicalGraph) -> str:
    text = graph.sensor_model.lower()
    component_text = " ".join(node.name.lower() for node in graph.component_nodes())
    joined = text + " " + component_text
    if any(k in joined for k in ["microphone", "digital audio", "i2s", "i²s"]):
        return "distorted digital audio output"
    if any(k in joined for k in ["rgb", "color", "clear photodiode"]):
        return "abnormal RGB/Clear color intensity"
    if any(k in joined for k in ["ccd", "camera", "video"]):
        return "distorted electrical video output"
    if any(k in joined for k in ["accelerometer", "acceleration"]):
        return "false acceleration"
    if any(k in joined for k in ["gyro", "angular"]):
        return "false angular velocity"
    if any(k in joined for k in ["distance", "ultrasonic"]):
        return "abnormal distance"
    return "other target-specific digital anomaly"


class CandidateExpansionGenerator:
    uses_structural_closure = True

    def __init__(
        self,
        model: str,
        rag_result: str,
        compact_context: str,
        max_api_attempts: int = 3,
        max_states_per_request: int = 6,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.model = model
        self.rag_result = rag_result
        self.compact_context = compact_context
        self.max_api_attempts = max(1, max_api_attempts)
        self.max_states_per_request = max(1, max_states_per_request)
        self.progress_callback = progress_callback
        self.calls = 0
        self.api_attempts = 0
        self.errors: List[Dict[str, Any]] = []
        self.prompt_records: List[Dict[str, Any]] = []
        self.response_records: List[Dict[str, Any]] = []

    def _report_progress(self, event: Dict[str, Any]) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(event)
        except Exception:
            # Progress reporting must never change graph-search results.
            pass

    def generate_layer(
        self,
        state_batch: List[Tuple[str, SearchState]],
        graph: SensorPhysicalGraph,
        registry: PhysicalOperatorRegistry,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not state_batch:
            return {}
        self.calls += 1
        frontier_states = [
            {
                "state_id": state_id,
                "state": state.to_dict(),
            }
            for state_id, state in state_batch
        ]
        grouped: Dict[str, List[Dict[str, Any]]] = {
            state_id: [] for state_id, _state in state_batch
        }
        invalid_candidates: List[Dict[str, Any]] = []
        failed_chunk_count = 0
        expansion_task = "mixed_layer_expansion"
        chunk_counter = 1
        compact_operators = dumps_compact(_compact_operator_context(expansion_task))
        chunk_frontier = [
            {
                "state_id": state_id,
                "expansion_task": _expansion_task_for_state(state, graph),
                "state": _compact_state_for_prompt(state),
            }
            for state_id, state in state_batch
        ]
        task_by_state_id = {
            item["state_id"]: item["expansion_task"]
            for item in chunk_frontier
        }
        local_context = dumps_compact(
            _compact_local_graph_context(graph, state_batch, expansion_task)
        )
        system_prompt, user_prompt = build_candidate_expansion_prompts(
            rag_result=_trim_text(self.rag_result, 2500),
            compact_context=_trim_text(self.compact_context, 3500),
            serialized_search_state=dumps_compact(chunk_frontier),
            serialized_sensor_graph="{}",
            serialized_allowed_operators=compact_operators,
            expansion_task=expansion_task,
            serialized_local_context=local_context,
        )
        self.prompt_records.append(
            {
                "layer_call": self.calls,
                "chunk_index": 0,
                "task_chunk_index": 0,
                "expansion_task": expansion_task,
                "state_ids": [state_id for state_id, _state in state_batch],
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        self._report_progress(
            {
                "event": "layer_started",
                "layer_call": self.calls,
                "frontier_size": len(state_batch),
                "max_api_attempts": self.max_api_attempts,
                "api_attempt_count": self.api_attempts,
            }
        )

        try:
            candidates = None
            request_error = None
            for attempt in range(self.max_api_attempts):
                self.api_attempts += 1
                self._report_progress(
                    {
                        "event": "api_attempt_started",
                        "layer_call": self.calls,
                        "frontier_size": len(state_batch),
                        "attempt": attempt + 1,
                        "max_attempts": self.max_api_attempts,
                        "api_attempt_count": self.api_attempts,
                    }
                )
                try:
                    response = chatanywhere_chat_completion(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        auth_header=chatanywhere_auth_header,
                        temperature=0.1,
                        timeout=900 if self.model == "minimax-m3" else 120,
                        max_tokens=16000 if self.model == "minimax-m3" else 6000,
                    )
                    raw = _extract_chat_content(response)
                    try:
                        payload = extract_json_payload(raw)
                    except (json.JSONDecodeError, ValueError):
                        if self.model != "minimax-m3":
                            raise
                        payload = _repair_candidate_json(raw, system_prompt, user_prompt)
                    parsed_candidates = payload.get("candidate_expansions", [])
                    if not isinstance(parsed_candidates, list):
                        raise ValueError("candidate_expansions is not a list")
                    candidates = parsed_candidates
                    request_error = None
                    self._report_progress(
                        {
                            "event": "api_attempt_succeeded",
                            "layer_call": self.calls,
                            "attempt": attempt + 1,
                            "max_attempts": self.max_api_attempts,
                            "raw_candidate_count": len(parsed_candidates),
                            "api_attempt_count": self.api_attempts,
                        }
                    )
                    break
                except Exception as exc:
                    request_error = exc
                    retry_delay = min(2 ** attempt, 4) if attempt + 1 < self.max_api_attempts else 0
                    self._report_progress(
                        {
                            "event": "api_attempt_failed",
                            "layer_call": self.calls,
                            "attempt": attempt + 1,
                            "max_attempts": self.max_api_attempts,
                            "api_attempt_count": self.api_attempts,
                            "retry_delay_seconds": retry_delay,
                            "error": str(exc)[:300],
                        }
                    )
                    if attempt + 1 < self.max_api_attempts:
                        time.sleep(retry_delay)
            if candidates is None:
                raise RuntimeError(
                    f"LLM request or JSON validation failed after "
                    f"{self.max_api_attempts} "
                    f"attempt(s): {request_error}"
                )

            valid_state_ids = {state_id for state_id, _state in state_batch}
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    invalid_candidates.append(
                        {"candidate": candidate, "reason": "not an object"}
                    )
                    continue
                state_id = str(candidate.get("state_id") or "")
                if not state_id and len(state_batch) == 1:
                    state_id = state_batch[0][0]
                if state_id not in valid_state_ids:
                    invalid_candidates.append(
                        {
                            "candidate": candidate,
                            "reason": "unknown or missing state_id",
                        }
                    )
                    continue
                if len(grouped[state_id]) >= 4:
                    continue

                # A mechanism selected on an ExternalSignalNode makes the
                # searcher immediately close that path through the fixed
                # architecture.  That skips sibling checks at the reached
                # component (for example, Photoelectric beside
                # Photoacoustic, or Saturation/Aliasing after Antenna
                # injection).  Normalize occasional prompt violations into a
                # reachability-only entry edge; the next layer will evaluate
                # mechanisms on the actual host structure.
                if (
                    task_by_state_id.get(state_id) == "entry_expansion"
                    and candidate.get("mechanism_name") not in (None, "", "null")
                ):
                    deferred_mechanism = candidate.get("mechanism_name")
                    relation_type = candidate.get("relation_type")
                    if relation_type == "apply":
                        relation_type = "couple"
                    candidate = {
                        **candidate,
                        "relation_type": relation_type or "couple",
                        "mechanism_name": None,
                        "deferred_mechanism_name": deferred_mechanism,
                    }

                physical_flags = candidate.get("physical_flags")
                if not isinstance(physical_flags, dict):
                    physical_flags = {}
                physical_claims = candidate.get("physical_claims")
                if not isinstance(physical_claims, list):
                    physical_claims = []
                for claim in physical_claims:
                    claim_name = str(claim or "").strip()
                    if claim_name in {
                        "out_of_band_input",
                        "nonzero_stopband_response",
                        "high_frequency_input",
                        "modulated_high_frequency_input",
                        "assume_microphone_ultrasonic_nonlinearity_prior",
                        "assume_microphone_photoacoustic_prior",
                        "assume_microphone_photoelectric_prior",
                        "assume_qualitative_overdrive",
                    }:
                        physical_flags[claim_name] = True

                target = candidate.get("proposed_target")
                if (
                    candidate.get("mechanism_name")
                    and isinstance(target, dict)
                    and target.get("node_type") == "MechanismNode"
                ):
                    candidate = {
                        **candidate,
                        "proposed_target": {
                            **target,
                            "node_type": "SignalStateNode",
                            "name": (
                                f"disturbed {target.get('modality') or 'electrical'} "
                                f"signal after {candidate.get('mechanism_name')}"
                            ),
                        },
                    }

                grouped[state_id].append(
                    {
                        **candidate,
                        **physical_flags,
                        "state_id": state_id,
                        "candidate_source": "llm",
                        "expansion_task": expansion_task,
                        "mandatory_preconditions": [],
                        "parameter_constraints": [],
                        "unknown_preconditions": [],
                        "retrieval_queries": [],
                    }
                )
        except Exception as exc:
            failed_chunk_count += 1
            self.errors.append(
                {
                    "frontier_states": chunk_frontier,
                    "layer_call": self.calls,
                    "chunk_index": 0,
                    "expansion_task": expansion_task,
                    "error": str(exc),
                    "fallback": "none; this frontier layer returns no LLM candidates",
                }
            )

        self.response_records.append(
            {
                "frontier_states": frontier_states,
                "candidate_expansions": [
                    candidate
                    for state_candidates in grouped.values()
                    for candidate in state_candidates
                ],
                "invalid_candidates": invalid_candidates,
                "chunk_count": chunk_counter,
                "failed_chunk_count": failed_chunk_count,
            }
        )
        self._report_progress(
            {
                "event": (
                    "layer_completed"
                    if failed_chunk_count == 0
                    else "layer_completed_with_chunk_errors"
                ),
                "layer_call": self.calls,
                "frontier_size": len(state_batch),
                "chunk_count": chunk_counter,
                "failed_chunk_count": failed_chunk_count,
                "candidate_count": sum(
                    len(items) for items in grouped.values()
                ),
                "invalid_candidate_count": len(invalid_candidates),
                "api_attempt_count": self.api_attempts,
            }
        )
        return {
            state_id: _merge_candidate_sets(state_candidates)
            for state_id, state_candidates in grouped.items()
        }
