from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .constants import ACTIVE, STATUS_TRUE, STATUS_UNKNOWN


@dataclass
class EvidenceRef:
    evidence_id: str
    source_type: str
    source_name: str
    locator: str
    content: str
    supports_claim: str
    evidence_scope: str
    reliability_level: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    name: str
    modality: str = ""
    component_category: str = ""
    component_name: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    evidence_status: str = STATUS_UNKNOWN
    source_stage: str = "search_generated"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    mechanism_name: Optional[str] = None
    attack_origin: str = ""
    input_modality: str = ""
    output_modality: str = ""
    mandatory_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    parameter_constraints: List[Dict[str, Any]] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    counter_evidence: List[str] = field(default_factory=list)
    type_status: str = STATUS_UNKNOWN
    evidence_status: str = STATUS_UNKNOWN
    constraint_status: str = STATUS_UNKNOWN
    final_status: str = STATUS_UNKNOWN
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MechanismInstance:
    mechanism_name: str
    source_component: str
    mechanism_node_id: str
    plain_language_analysis: str
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchState:
    signal_origin: str
    current_node_id: str
    visited_node_ids: List[str] = field(default_factory=list)
    path_edge_ids: List[str] = field(default_factory=list)
    mechanism_instances: List[MechanismInstance] = field(default_factory=list)
    unknown_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    false_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    accumulated_evidence: List[str] = field(default_factory=list)
    depth: int = 0
    path_score: float = 0.0
    status: str = ACTIVE
    structural_resume_node_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["mechanism_instances"] = [item.to_dict() for item in self.mechanism_instances]
        return data


@dataclass
class MechanismPath:
    path_id: str
    status: str
    external_signal: Dict[str, Any]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    mechanism_instances: List[MechanismInstance]
    observable_output: str
    mandatory_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    unknown_preconditions: List[Dict[str, Any]] = field(default_factory=list)
    counter_evidence: List[Dict[str, Any]] = field(default_factory=list)
    relevant_parameter_refs: List[str] = field(default_factory=list)
    relevant_sensor_parameters: List[Dict[str, Any]] = field(default_factory=list)
    path_score: float = 0.0
    rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "status": self.status,
            "external_signal": self.external_signal,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "mechanism_instances": [item.to_dict() for item in self.mechanism_instances],
            "observable_output": self.observable_output,
            "mandatory_preconditions": self.mandatory_preconditions,
            "unknown_preconditions": self.unknown_preconditions,
            "counter_evidence": self.counter_evidence,
            "relevant_parameter_refs": self.relevant_parameter_refs,
            "relevant_sensor_parameters": self.relevant_sensor_parameters,
            "path_score": self.path_score,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class SearchConfig:
    max_depth: int = 8
    beam_width: int = 12
    max_paths_per_signal: int = 12
    max_unknown_edges: int = 2
    # One expansion now covers the entire active frontier layer.
    max_llm_expansions: int = 8
    accepted_path_limit: int = 36
    random_seed: int = 0
    deduplicate_paths: bool = True


class SensorPhysicalGraph:
    def __init__(self, sensor_model: str = "unknown") -> None:
        self.sensor_model = sensor_model
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.evidence: Dict[str, EvidenceRef] = {}
        self.sensor_parameters: Dict[str, Dict[str, Any]] = {}
        self._node_counter = 0
        self._edge_counter = 0

    def next_node_id(self, prefix: str = "n") -> str:
        self._node_counter += 1
        return f"{prefix}_{self._node_counter}"

    def next_edge_id(self, prefix: str = "e") -> str:
        self._edge_counter += 1
        return f"{prefix}_{self._edge_counter}"

    def add_evidence(self, evidence: EvidenceRef) -> EvidenceRef:
        self.evidence[evidence.evidence_id] = evidence
        return evidence

    def add_node(self, node: GraphNode) -> GraphNode:
        existing = self.find_node(
            node_type=node.node_type,
            name=node.name,
            component_name=node.component_name,
            modality=node.modality,
        )
        if existing:
            return existing
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        self.edges[edge.edge_id] = edge
        return edge

    def find_node(
        self,
        node_type: str,
        name: str,
        component_name: str = "",
        modality: str = "",
    ) -> Optional[GraphNode]:
        lname = (name or "").strip().lower()
        lc = (component_name or "").strip().lower()
        lm = (modality or "").strip().lower()
        for node in self.nodes.values():
            if node.node_type != node_type:
                continue
            if (node.name or "").strip().lower() != lname:
                continue
            if lc and (node.component_name or "").strip().lower() != lc:
                continue
            if lm and (node.modality or "").strip().lower() != lm:
                continue
            return node
        return None

    def component_exists(self, component_name: str) -> bool:
        target = (component_name or "").strip().lower()
        if not target:
            return False
        return any(
            node.node_type in {"ComponentNode", "BoundaryNode"}
            and (
                node.name.lower() == target
                or node.component_name.lower() == target
                or target in {
                    str(alias or "").strip().lower()
                    for alias in node.attributes.get("collapsed_aliases", [])
                }
            )
            for node in self.nodes.values()
        )

    def component_evidence_status(self, component_name: str) -> str:
        target = (component_name or "").strip().lower()
        if not target:
            return STATUS_UNKNOWN
        matches = [
            node
            for node in self.nodes.values()
            if node.node_type in {"ComponentNode", "BoundaryNode"}
            and (
                (node.name or "").strip().lower() == target
                or (node.component_name or "").strip().lower() == target
                or target in {
                    str(alias or "").strip().lower()
                    for alias in node.attributes.get("collapsed_aliases", [])
                }
            )
        ]
        if any(node.evidence_status == STATUS_TRUE for node in matches):
            return STATUS_TRUE
        return STATUS_UNKNOWN

    def component_nodes(self) -> List[GraphNode]:
        return [node for node in self.nodes.values() if node.node_type == "ComponentNode"]

    def boundary_nodes(self) -> List[GraphNode]:
        return [node for node in self.nodes.values() if node.node_type == "BoundaryNode"]

    def outgoing(self, node_id: str) -> List[GraphEdge]:
        return [edge for edge in self.edges.values() if edge.source_node_id == node_id]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor_model": self.sensor_model,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges.values()],
            "evidence": [evidence.to_dict() for evidence in self.evidence.values()],
            "sensor_parameter_catalog": list(self.sensor_parameters.values()),
        }

    def summary(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for node in self.nodes.values():
            by_type[node.node_type] = by_type.get(node.node_type, 0) + 1
        return {
            "sensor_model": self.sensor_model,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "sensor_parameter_count": len(self.sensor_parameters),
            "nodes_by_type": by_type,
            "components": [
                {
                    "name": node.component_name or node.name,
                    "category": node.component_category,
                    "evidence_status": node.evidence_status,
                    "source_stage": node.source_stage,
                    "inference_reason": node.attributes.get("inference_reason", ""),
                    "parameter_refs": node.attributes.get("parameter_refs", []),
                }
                for node in self.component_nodes() + self.boundary_nodes()
            ],
        }
