from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Tuple

from .component_ontology import component_capabilities, infer_component_priors
from .constants import BOUNDARY_KEYWORDS, SIGNAL_ORIGINS, STATUS_FALSE, STATUS_TRUE, STATUS_UNKNOWN
from .mechanism_taxonomy import canonical_component_category, classify_component_name
from .models import EvidenceRef, GraphEdge, GraphNode, SensorPhysicalGraph
from .sensor_parameters import extract_sensor_parameters


ABSTRACT_COMPONENT_NAMES: Dict[str, str] = {
    "Acoustic Transducer": "acoustic transducer",
    "Optical Transducer": "optical transducer",
    "Electromagnetic Transducer": "electromagnetic transducer",
    "Force Transducer": "force/mechanical transducer",
    "Transducer Module": "transducer module",
    "Signal Conditioning Circuits": "signal conditioning circuits",
    "Amplifier": "analog front-end / amplifier",
    "Filter": "signal filter",
    "ADC": "ADC / sampling stage",
    "DSP": "digital processing",
    "Communication Interface": "communication interface",
    "Auxiliary Module": "auxiliary access path",
    "Power Supply": "power supply path",
    "Wires": "conductive interconnects",
    "Clock Oscillator": "clock oscillator",
}


def _flatten_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: List[str] = []
        for key, item in value.items():
            result.extend(_flatten_strings(key))
            result.extend(_flatten_strings(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for item in value:
            result.extend(_flatten_strings(item))
        return result
    return [str(value)]


def _sensor_text(sensor_info: Any) -> str:
    if isinstance(sensor_info, str):
        return sensor_info
    return json.dumps(sensor_info, ensure_ascii=False, indent=2)


def _semantic_sensor_text(sensor_info: Any) -> str:
    """Return free Step1 text without rescanning already-structured component rows."""
    if not isinstance(sensor_info, dict):
        return _sensor_text(sensor_info)
    structured_keys = {
        "components",
        "sensor_components",
        "Component",
        "component_list",
        "hardware_components",
    }
    free_text_payload = {
        key: value for key, value in sensor_info.items() if key not in structured_keys
    }
    return _sensor_text(free_text_payload)


def _extract_sensor_model(sensor_info: Any) -> str:
    if isinstance(sensor_info, dict):
        for key in ("sensor_model", "model", "name", "sensor_name", "Sensor Model", "Sensor Name"):
            value = sensor_info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        rag = sensor_info.get("rag_input")
        if isinstance(rag, str) and rag.strip():
            return rag.strip()
    text = _sensor_text(sensor_info)
    model_match = re.search(r"Sensor Models?\*\*:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if model_match:
        return model_match.group(1).strip()
    model_match = re.search(r"Sensor Models?:\s*([^\n]+)", text, flags=re.IGNORECASE)
    if model_match:
        return model_match.group(1).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:80] or "unknown"


def _component_items_from_structured(sensor_info: Any) -> List[Dict[str, str]]:
    if not isinstance(sensor_info, dict):
        return []
    candidates = []
    for key in ("components", "sensor_components", "Component", "component_list", "hardware_components"):
        value = sensor_info.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    items: List[Dict[str, str]] = []
    for item in candidates:
        if isinstance(item, str):
            items.append({"name": item, "category": classify_component_name(item)})
        elif isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("component_name")
                or item.get("Component")
                or item.get("component")
                or item.get("module")
            )
            category = item.get("category") or item.get("component_category") or item.get("type")
            if name:
                items.append({"name": str(name), "category": canonical_component_category(category) or classify_component_name(name)})
    return items


SEMANTIC_COMPONENT_PATTERNS: List[Tuple[str, str]] = [
    (r"\bMEMS\s+microphone\b|\bmicrophone\b", "Acoustic Transducer"),
    (
        r"\bultrasonic\s+(?:transmitters?|receivers?|transducers?)\b"
        r"|\bwaterproof\s+(?:probe|transducer)\b"
        r"|\bultrasonic\s+ranging\s+module\b",
        "Acoustic Transducer",
    ),
    (
        r"\bMEMS\s+proof\s+mass\b|\bproof\s+mass\b|\bvibratory\s+MEMS\b"
        r"|\bpolysilicon\s+surface[-\s]?micromachined\s+structure\b"
        r"|\bdifferential\s+capacitors?\b|\bcapacitive\s+pickoff\b"
        r"|\bMEMS\s+diaphragm\b|\bpressure\s+diaphragm\b"
        r"|\bspring\s+type\s+trigger\s+switch\b",
        "Force Transducer",
    ),
    (
        r"\b(?:RGB|clear|color)[-\s]?(?:filtered\s+)?photodiodes?\b"
        r"|\bphotodiode\s+array\b|\barray\s+of\s+photodiodes?\b"
        r"|\bphotodiodes?\b|\bphototransistor\b|\binfrared\s+emitter\b"
        r"|\bCCD(?:\s+array)?\b|\bCMOS(?:\s+array|\s+image\s+sensor)\b"
        r"|\bphoto[-\s]?current\b|\bphotocurrent\b|\bsensitive\s+to\s+light\b",
        "Optical Transducer",
    ),
    (
        r"\banalog\s+front[-\s]?end\b|\bAFE\b|\bsignal\s+conditioning(?:\s+circuits?)?\b"
        r"|\bprogrammable\s+analog\s+gain\b|\bcharge\s+amplifier(?:\s+circuitry)?\b"
        r"|\bamplifiers?\b|\bsource\s+follower\b|\bcontrol\s+circuit\b"
        r"|\bdemodulator\b",
        "Amplifier",
    ),
    (
        r"\bdigital\s+anti[-\s]?aliasing(?:/band[-\s]?pass)?\s+filters?\b"
        r"|\banti[-\s]?alias\s+filters?\b|\blow[-\s]?pass\s+filters?\b"
        r"|\bnotch\s+filters?\b|\bfilter(?:s|\s+block)?\b",
        "Filter",
    ),
    (
        r"\bsigma[-\s]?delta\s+(?:analog[-\s]?to[-\s]?digital\s+converters?|ADCs?)\b"
        r"|\bΣ[-\s]?Δ\s+(?:analog[-\s]?to[-\s]?digital\s+converters?|ADCs?)\b"
        r"|\banalog[-\s]?to[-\s]?digital\s+converters?\b|\bADCs?\b",
        "ADC",
    ),
    (
        r"\bDSP\b|\bdigital\s+(?:signal\s+)?processing\b|\bdigital\s+motion\s+processor\b"
        r"|\bDMP\b|\bstate\s+machine\b",
        "DSP",
    ),
    (
        r"\bI2C\b|\bI²C\b|\bI2S\b|\bI²S\b|\bSPI\b|\bUART\b"
        r"|\bcommunication\s+interface\b|\bdigital\s+interface\b"
        r"|\bshift\s+register\b",
        "Communication Interface",
    ),
    (
        r"\b(?:SCK|SD|WS|L/R|CHIPEN|VDD|GND)\s*(?:pin|pins)?\b|\bpins?\b"
        r"|\bPCB\s+(?:trace|traces)\b|\bconductive\s+(?:pin|pins|trace|traces|contacts?|pick\s+feet)\b"
        r"|\binternal\s+metal\s+spring\s+contacts?\b|\boutput\s+contact\s+interface\b"
        r"|\bexposed\s+pins?\b|\bwires?\b|\bcables?\b|\bleads?\b",
        "Wires",
    ),
    (r"\bpower\s+management\b|\bpower\s+(?:supply|line|lines|path)\b|\bVDD\b", "Power Supply"),
    (
        r"\bclock\s+oscillator\b|\brelaxation\s+oscillator\b|\bMEMS\s+oscillator\b",
        "Clock Oscillator",
    ),
    (r"\bbottom[-\s]?port\b|\bacoustic\s+port\b|\boptical\s+window\b", "Auxiliary Module"),
]


def _semantic_component_mentions(text: str) -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen = set()
    for pattern, category in SEMANTIC_COMPONENT_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            name = match.group(0).strip()
            key = (name.lower(), category)
            if key in seen:
                continue
            seen.add(key)
            found.append({"name": name, "category": category})
    return found


def _explicit_components(sensor_info: Any) -> List[Dict[str, str]]:
    structured = _component_items_from_structured(sensor_info)
    text = _semantic_sensor_text(sensor_info)
    detected = _semantic_component_mentions(text)
    merged: Dict[str, Dict[str, str]] = {}
    for item in structured + detected:
        name = str(item.get("name") or "").strip()
        category = canonical_component_category(item.get("category")) or classify_component_name(name)
        if not name:
            continue
        merged[name.lower()] = {"name": name, "category": category}
    return list(merged.values())


def _is_boundary_component(name: str, category: str) -> bool:
    lowered = name.lower()
    return category == "Wires" or "pin" in lowered or any(keyword in lowered for keyword in BOUNDARY_KEYWORDS)


def _make_step1_evidence(graph: SensorPhysicalGraph, sensor_info: Any) -> EvidenceRef:
    evidence = EvidenceRef(
        evidence_id="ev_step1_sensor_info",
        source_type="datasheet",
        source_name="Step1 Sensor Information",
        locator="step1_output.json",
        content=_sensor_text(sensor_info)[:4000],
        supports_claim="Target-specific sensor structure and extracted components.",
        evidence_scope="target_specific",
        reliability_level="high",
    )
    return graph.add_evidence(evidence)


def _has_microphone_prior(sensor_info: Any, graph: SensorPhysicalGraph) -> bool:
    text = _sensor_text(sensor_info).lower()
    if any(keyword in text for keyword in ["microphone", "mems microphone", "麦克风"]):
        return True
    return any(
        "microphone" in f"{node.name} {node.component_name}".lower()
        for node in graph.component_nodes()
    )


def _has_optical_shield_counterevidence(sensor_info: Any) -> bool:
    text = _sensor_text(sensor_info).lower()
    shield_keywords = [
        "optically shielded",
        "light shielded",
        "opaque package",
        "opaque metal package",
        "sealed metal can",
        "metal shield",
        "shielding can",
        "no optical access",
        "光学屏蔽",
        "遮光",
        "不透光",
        "金属屏蔽壳",
        "屏蔽壳",
        "无光学入口",
    ]
    return any(keyword in text for keyword in shield_keywords)


def _add_inferred_microphone_optical_prior(graph: SensorPhysicalGraph, sensor_info: Any) -> None:
    if not _has_microphone_prior(sensor_info, graph):
        return

    shielded = _has_optical_shield_counterevidence(sensor_info)
    status = STATUS_FALSE if shielded else STATUS_TRUE
    evidence = graph.add_evidence(
        EvidenceRef(
            evidence_id="ev_expert_microphone_optical_prior",
            source_type="expert_knowledge",
            source_name="Microphone optical-effect prior",
            locator="step2_graph.graph_builder",
            content=(
                "For microphone-class sensors, optical access through a port/package and light interaction "
                "with MEMS/ASIC structures are treated as default expert-knowledge priors for searching "
                "photoacoustic and photoelectric mechanisms, unless Step1 explicitly states optical shielding."
            ),
            supports_claim="Microphone-class sensors may expose optical-entry/photo-sensitive structures relevant to Photoacoustic Effect and Photoelectric Effect.",
            evidence_scope="generic_physics",
            reliability_level="medium",
        )
    )
    attributes = {
        "inferred_default": True,
        "counterevidence_rule": "Rejected if Step1 explicitly states optical shielding or opaque/shielded package.",
        "optical_shield_counterevidence": shielded,
    }
    graph.add_node(
        GraphNode(
            node_id=graph.next_node_id("boundary"),
            node_type="BoundaryNode",
            name="inferred optical access through microphone port/package",
            modality="optical",
            component_category="Auxiliary Module",
            component_name="microphone optical access",
            attributes=dict(attributes),
            evidence_refs=[evidence.evidence_id],
            evidence_status=status,
            source_stage="expert_knowledge",
        )
    )
    graph.add_node(
        GraphNode(
            node_id=graph.next_node_id("component"),
            node_type="ComponentNode",
            name="inferred photosensitive MEMS/ASIC junctions",
            modality="electrical",
            component_category="Signal Conditioning Circuits",
            component_name="photosensitive MEMS/ASIC junctions",
            attributes=dict(attributes),
            evidence_refs=[evidence.evidence_id],
            evidence_status=status,
            source_stage="expert_knowledge",
        )
    )


def _add_component_knowledge_priors(graph: SensorPhysicalGraph, sensor_info: Any) -> None:
    """Complete only roles still absent after exhaustive Step1 extraction."""
    priors = infer_component_priors(_sensor_text(sensor_info))
    if not priors:
        return
    evidence = graph.add_evidence(
        EvidenceRef(
            evidence_id="ev_expert_component_ontology",
            source_type="expert_knowledge",
            source_name="Sensor component ontology and class priors",
            locator="step2_graph.component_ontology",
            content=(
                "After Step1-explicit components are extracted, missing physical roles are completed "
                "from the sensor component ontology: transducer, signal conditioning, computing and "
                "communication, and auxiliary modules."
            ),
            supports_claim="Minimum physically necessary components may be inferred from sensor class and output form.",
            evidence_scope="generic_physics",
            reliability_level="medium",
        )
    )
    existing_categories = {
        node.component_category for node in graph.component_nodes() + graph.boundary_nodes()
    }
    for prior in priors:
        category = prior["category"]
        if category in existing_categories:
            continue
        capabilities = component_capabilities(category)
        node_type = "BoundaryNode" if category == "Wires" else "ComponentNode"
        graph.add_node(
            GraphNode(
                node_id=graph.next_node_id("boundary" if node_type == "BoundaryNode" else "component"),
                node_type=node_type,
                name=prior["name"],
                modality=(capabilities.get("output_modalities") or [""])[0],
                component_category=category,
                component_name=prior["name"],
                attributes={
                    "inferred_default": True,
                    "inference_reason": prior["reason"],
                    "ontology_module": capabilities.get("module", ""),
                    "input_modalities": capabilities.get("input_modalities", []),
                    "output_modalities": capabilities.get("output_modalities", []),
                },
                evidence_refs=[evidence.evidence_id],
                evidence_status=STATUS_TRUE,
                source_stage="expert_knowledge",
            )
        )
        existing_categories.add(category)


def _add_external_signals(graph: SensorPhysicalGraph) -> None:
    for modality in SIGNAL_ORIGINS:
        graph.add_node(
            GraphNode(
                node_id=f"external_{modality}",
                node_type="ExternalSignalNode",
                name=f"external {modality} signal",
                modality=modality,
                evidence_status=STATUS_TRUE,
                source_stage="expert_knowledge",
            )
        )


def _chain_order(node: GraphNode) -> int:
    category = node.component_category
    order = {
        "Acoustic Transducer": 10,
        "Optical Transducer": 10,
        "Electromagnetic Transducer": 10,
        "Force Transducer": 10,
        "Signal Conditioning Circuits": 20,
        "Amplifier": 20,
        "Filter": 30,
        "ADC": 40,
        "DSP": 50,
        "Communication Interface": 60,
    }
    return order.get(category, 100)


def _add_known_processing_chain(graph: SensorPhysicalGraph) -> None:
    stages: Dict[int, List[GraphNode]] = {}
    for node in graph.component_nodes():
        order = _chain_order(node)
        if order < 100:
            stages.setdefault(order, []).append(node)
    stage_orders = sorted(stages)
    for left_order, right_order in zip(stage_orders, stage_orders[1:]):
        for left in stages[left_order]:
            for right in stages[right_order]:
                relation = "sample" if right.component_category == "ADC" else "propagate"
                graph.add_edge(
                    GraphEdge(
                        edge_id=graph.next_edge_id("structure"),
                        source_node_id=left.node_id,
                        target_node_id=right.node_id,
                        relation_type=relation,
                        input_modality=left.modality or "electrical",
                        output_modality=right.modality or "electrical",
                        type_status=STATUS_TRUE,
                        evidence_status=STATUS_TRUE,
                        constraint_status=STATUS_TRUE,
                        final_status=STATUS_TRUE,
                        explanation="Processing-chain adjacency derived from component ontology stage order.",
                    )
                )


def _merge_status(statuses: Iterable[str]) -> str:
    values = set(statuses)
    if STATUS_TRUE in values:
        return STATUS_TRUE
    if values == {STATUS_FALSE}:
        return STATUS_FALSE
    return STATUS_UNKNOWN


def _source_stage_priority(source_stage: str) -> int:
    return {"step1": 0, "expert_knowledge": 1, "search_generated": 2, "llm_inferred": 3}.get(source_stage, 4)


def _abstract_component_name(category: str, fallback: str) -> str:
    return ABSTRACT_COMPONENT_NAMES.get(category) or fallback


def _collapse_component_architecture(graph: SensorPhysicalGraph) -> None:
    """Collapse Step1/expert components to the coarse roles used by Step2 mechanism search."""
    structural_nodes = [
        node for node in graph.nodes.values()
        if node.node_type in {"ComponentNode", "BoundaryNode"}
    ]
    groups: Dict[Tuple[str, str], List[GraphNode]] = {}
    for node in structural_nodes:
        category = node.component_category or classify_component_name(node.component_name or node.name)
        if not category:
            continue
        node_type = "BoundaryNode" if category == "Wires" or node.node_type == "BoundaryNode" else "ComponentNode"
        groups.setdefault((node_type, category), []).append(node)

    collapsed: Dict[str, GraphNode] = {
        node_id: node
        for node_id, node in graph.nodes.items()
        if node.node_type not in {"ComponentNode", "BoundaryNode"}
    }
    old_to_new: Dict[str, str] = {}
    for (node_type, category), nodes in groups.items():
        nodes.sort(key=lambda item: (_source_stage_priority(item.source_stage), item.node_id))
        representative = nodes[0]
        aliases = []
        evidence_refs = []
        sources = []
        for node in nodes:
            old_to_new[node.node_id] = representative.node_id
            for alias in [node.name, node.component_name]:
                if alias and alias not in aliases:
                    aliases.append(alias)
            for evidence_ref in node.evidence_refs:
                if evidence_ref not in evidence_refs:
                    evidence_refs.append(evidence_ref)
            if node.source_stage not in sources:
                sources.append(node.source_stage)
        capabilities = component_capabilities(category)
        representative.node_type = node_type
        representative.name = _abstract_component_name(category, representative.name)
        representative.component_name = representative.name
        representative.component_category = category
        representative.modality = representative.modality or (capabilities.get("output_modalities") or [""])[0]
        representative.evidence_refs = evidence_refs
        representative.evidence_status = _merge_status(node.evidence_status for node in nodes)
        representative.source_stage = min((node.source_stage for node in nodes), key=_source_stage_priority)
        representative.attributes = {
            **representative.attributes,
            "architecture_abstraction": "component_category",
            "collapsed_component_count": len(nodes),
            "collapsed_aliases": aliases,
            "collapsed_source_stages": sources,
            "ontology_module": capabilities.get("module", representative.attributes.get("ontology_module", "")),
            "input_modalities": capabilities.get("input_modalities", representative.attributes.get("input_modalities", [])),
            "output_modalities": capabilities.get("output_modalities", representative.attributes.get("output_modalities", [])),
        }
        collapsed[representative.node_id] = representative

    graph.nodes = collapsed
    remapped_edges: Dict[Tuple[str, str, str, str, str], GraphEdge] = {}
    for edge in graph.edges.values():
        source_id = old_to_new.get(edge.source_node_id, edge.source_node_id)
        target_id = old_to_new.get(edge.target_node_id, edge.target_node_id)
        if source_id == target_id:
            continue
        edge.source_node_id = source_id
        edge.target_node_id = target_id
        key = (
            edge.source_node_id,
            edge.target_node_id,
            edge.relation_type,
            edge.mechanism_name or "",
            edge.attack_origin,
        )
        if key not in remapped_edges:
            remapped_edges[key] = edge
    graph.edges = {edge.edge_id: edge for edge in remapped_edges.values()}


def _attach_step1_parameters(graph: SensorPhysicalGraph, sensor_info: Any) -> None:
    """Attach Step1 parameters to the coarse component roles used by path search."""
    catalog = extract_sensor_parameters(sensor_info)
    graph.sensor_parameters = {
        str(parameter["parameter_id"]): parameter for parameter in catalog
    }
    for node in graph.component_nodes() + graph.boundary_nodes():
        aliases = " ".join(
            str(value or "")
            for value in (
                node.name,
                node.component_name,
                *(node.attributes.get("collapsed_aliases") or []),
            )
        ).casefold()
        matched = []
        for parameter in catalog:
            categories = set(parameter.get("component_categories") or [])
            raw_text = str(parameter.get("raw_text") or "").casefold()
            category_match = node.component_category in categories
            alias_match = any(
                token in raw_text and token in aliases
                for token in ("cable", "wire", "trace", "pin", "adc", "baud", "serial", "filter", "voltage", "current")
            )
            if category_match or alias_match:
                matched.append(parameter)
        node.attributes["parameter_refs"] = [
            parameter["parameter_id"] for parameter in matched
        ]
        node.attributes["sensor_parameters"] = matched


class GraphBuilder:
    def build(self, sensor_info: Any) -> SensorPhysicalGraph:
        graph = SensorPhysicalGraph(sensor_model=_extract_sensor_model(sensor_info))
        evidence = _make_step1_evidence(graph, sensor_info)
        _add_external_signals(graph)

        for item in _explicit_components(sensor_info):
            name = item["name"]
            category = canonical_component_category(item.get("category")) or classify_component_name(name)
            node_type = "BoundaryNode" if _is_boundary_component(name, category) else "ComponentNode"
            modality = "electrical" if category in {"Amplifier", "Filter", "ADC", "DSP", "Communication Interface", "Wires", "Power Supply"} else ""
            capabilities = component_capabilities(category)
            graph.add_node(
                GraphNode(
                    node_id=graph.next_node_id("component" if node_type == "ComponentNode" else "boundary"),
                    node_type=node_type,
                    name=name,
                    modality=modality,
                    component_category=category,
                    component_name=name,
                    attributes={
                        "ontology_module": capabilities.get("module", ""),
                        "input_modalities": capabilities.get("input_modalities", []),
                        "output_modalities": capabilities.get("output_modalities", []),
                        "extraction_source": "step1_semantic",
                    },
                    evidence_refs=[evidence.evidence_id],
                    evidence_status=STATUS_TRUE,
                    source_stage="step1",
                )
            )

        _add_component_knowledge_priors(graph, sensor_info)
        _add_inferred_microphone_optical_prior(graph, sensor_info)
        _collapse_component_architecture(graph)
        _attach_step1_parameters(graph, sensor_info)
        _add_known_processing_chain(graph)
        return graph
