from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from .constants import (
    ACCEPTED,
    ACTIVE,
    ALLOWED_MECHANISMS,
    NORMAL_RELATIONS,
    REJECTED,
    SIGNAL_ORIGINS,
    STATUS_FALSE,
    STATUS_TRUE,
    STATUS_UNKNOWN,
    UNRESOLVED,
)
from .constraint_checker import ParameterConstraintChecker
from .evidence_checker import EvidenceScopeChecker
from .mechanism_taxonomy import canonical_mechanism
from .models import GraphEdge, GraphNode, MechanismInstance, MechanismPath, SearchConfig, SearchState, SensorPhysicalGraph
from .operator_registry import PhysicalOperatorRegistry
from .path_scorer import PathScorer
from .scope_policy import Step2AttackScopePolicy
from .surviving_candidates import collect_surviving_path_mechanism_candidates
from .sensor_parameters import parameters_for_path


class MechanismGraphSearcher:
    def __init__(
        self,
        graph: SensorPhysicalGraph,
        generator: Optional[Any] = None,
        config: Optional[SearchConfig] = None,
        registry: Optional[PhysicalOperatorRegistry] = None,
    ) -> None:
        self.graph = graph
        self.generator = generator
        self.config = config or SearchConfig()
        self.registry = registry or PhysicalOperatorRegistry()
        self.evidence_checker = EvidenceScopeChecker()
        self.constraint_checker = ParameterConstraintChecker()
        self.scorer = PathScorer()
        self.scope_policy = Step2AttackScopePolicy(graph)
        self.scope_policy.annotate_origin_nodes()
        self.signal_coverage: Dict[str, str] = {}
        self.logs: List[Dict[str, Any]] = []
        self.accepted_paths: List[MechanismPath] = []
        self.unresolved_paths: List[MechanismPath] = []
        self.rejected_paths: List[MechanismPath] = []
        self.llm_expansions = 0
        self.analyzed_frontier_nodes: Set[Tuple[Any, ...]] = set()

    def search(self) -> Dict[str, Any]:
        if self.generator is None:
            raise RuntimeError(
                "MechanismGraphSearcher requires an explicit candidate generator; "
                "production Step2 must pass CandidateExpansionGenerator."
            )
        if not hasattr(self.generator, "generate_layer"):
            raise RuntimeError(
                "Candidate generator must implement generate_layer(); "
                "per-state LLM generation is not allowed."
            )

        frontier: List[SearchState] = []
        for signal in SIGNAL_ORIGINS:
            if self.scope_policy.skip_origin(signal):
                self.signal_coverage[signal] = "filtered_in_band"
                self.logs.append(
                    {
                        "event": "filtered_in_band_origin",
                        "signal_origin": signal,
                        "reason": "signal is the sensor's intended in-band input",
                    }
                )
                continue
            self.signal_coverage[signal] = "searched"
            start_id = f"external_{signal}"
            if start_id not in self.graph.nodes:
                continue
            frontier.append(
                SearchState(
                    signal_origin=signal,
                    current_node_id=start_id,
                    visited_node_ids=[start_id],
                    depth=0,
                    path_score=0.0,
                    status=ACTIVE,
                )
            )

        max_layer_calls = min(self.config.max_depth, self.config.max_llm_expansions)
        layer_index = 0
        while frontier and layer_index < max_layer_calls:
            eligible: List[SearchState] = []
            for state in frontier:
                if state.depth >= self.config.max_depth:
                    self._record_unresolved(state, "max_depth reached before observable output")
                    continue
                analysis_key = self._frontier_query_key(state)
                if analysis_key in self.analyzed_frontier_nodes:
                    self.logs.append(
                        {
                            "event": "frontier_node_already_analyzed",
                            "signal_origin": state.signal_origin,
                            "current_node_id": state.current_node_id,
                            "frontier_query_key": analysis_key,
                        }
                    )
                    continue
                eligible.append(state)
            frontier = self._prune_frontier(eligible)
            if not frontier:
                break

            query_batch, query_groups = self._group_frontier_queries(frontier, layer_index)
            self.llm_expansions += 1
            candidates_by_state = self.generator.generate_layer(
                query_batch,
                self.graph,
                self.registry,
            )
            self.analyzed_frontier_nodes.update(
                self._frontier_query_key(state)
                for _state_id, state in query_batch
            )
            self.logs.append(
                {
                    "event": "frontier_layer_proposal",
                    "layer_index": layer_index,
                    "llm_call_index": self.llm_expansions,
                    "frontier_size": len(frontier),
                    "query_frontier_size": len(query_batch),
                    "query_groups": {
                        query_id: {
                            "representative_state_id": query_id,
                            "member_state_ids": [
                                member_id for member_id, _member_state in members
                            ],
                        }
                        for query_id, members in query_groups.items()
                    },
                    "candidate_count": sum(
                        len(candidates_by_state.get(state_id, []))
                        for state_id, _state in query_batch
                    ),
                    "state_ids": [
                        member_id
                        for members in query_groups.values()
                        for member_id, _member_state in members
                    ],
                    "query_state_ids": [state_id for state_id, _state in query_batch],
                }
            )

            next_frontier: List[SearchState] = []
            for query_id, members in query_groups.items():
                candidates = candidates_by_state.get(query_id, [])
                representative_state = dict(query_batch)[query_id]
                for state_id, state in members:
                    self.logs.append(
                        {
                            "event": "candidate_proposal",
                            "layer_index": layer_index,
                            "state_id": state_id,
                            "query_state_id": query_id,
                            "state": state.to_dict(),
                            "candidate_count": len(candidates),
                            "candidates": candidates,
                        }
                    )
                    if not candidates:
                        self._record_unresolved(
                            state,
                            "LLM returned no valid candidates for this merged frontier query",
                        )
                    for candidate in candidates:
                        member_candidate = self._rebind_candidate_to_member(
                            candidate,
                            representative_state,
                            state,
                        )
                        new_state = self._apply_candidate(state, member_candidate)
                        if new_state is None:
                            continue
                        if new_state.status == ACTIVE:
                            if getattr(self.generator, "uses_structural_closure", False):
                                if new_state.mechanism_instances:
                                    closure_states = self._expand_structural_closure(new_state)
                                    completed_before = (
                                        len(self.accepted_paths)
                                        + len(self.unresolved_paths)
                                    )
                                    self._finalize_structural_outputs(closure_states)
                                    followups = self._mechanism_followup_frontier(
                                        new_state, closure_states
                                    )
                                    next_frontier.extend(followups)
                                    completed_after = (
                                        len(self.accepted_paths)
                                        + len(self.unresolved_paths)
                                    )
                                    if not followups and completed_after == completed_before:
                                        # This branch survived every physical/evidence
                                        # check but the Step1 architecture has no known
                                        # route to an observable-output node.  Preserve
                                        # it as unresolved instead of silently dropping
                                        # it; rejected branches remain excluded.
                                        self._record_unresolved(
                                            new_state,
                                            "mechanism path survived adjudication but no "
                                            "observable-output continuation is represented "
                                            "in the Step1 architecture",
                                        )
                                else:
                                    next_frontier.append(new_state)
                            else:
                                next_frontier.append(new_state)
            frontier = next_frontier
            layer_index += 1

        for state in frontier:
            self._record_unresolved(
                state,
                f"maximum batched LLM layer calls reached ({max_layer_calls})",
            )
        self._deduplicate()
        return self._result()

    def _expand_structural_closure(self, state: SearchState) -> List[SearchState]:
        queue = [state]
        expanded: List[SearchState] = []
        seen = {tuple(state.visited_node_ids)}

        while queue:
            current_state = queue.pop(0)
            structural_source_id = (
                current_state.structural_resume_node_id
                or current_state.current_node_id
            )
            structural_edges = [
                edge
                for edge in self.graph.outgoing(structural_source_id)
                if edge.edge_id.startswith("structure_")
                and not edge.mechanism_name
                and edge.final_status == STATUS_TRUE
                and edge.target_node_id in self.graph.nodes
                and edge.target_node_id not in current_state.visited_node_ids
            ]
            if not structural_edges:
                if current_state is state and not expanded:
                    expanded.append(current_state)
                continue

            for edge in structural_edges:
                target = self.graph.nodes[edge.target_node_id]
                path_edge = edge
                if current_state.structural_resume_node_id:
                    path_edge = self.graph.add_edge(
                        GraphEdge(
                            edge_id=self.graph.next_edge_id("structure_resume"),
                            source_node_id=current_state.current_node_id,
                            target_node_id=edge.target_node_id,
                            relation_type=edge.relation_type,
                            attack_origin=current_state.signal_origin,
                            input_modality=(
                                self.graph.nodes[
                                    current_state.current_node_id
                                ].modality
                                or current_state.signal_origin
                            ),
                            output_modality=target.modality,
                            supporting_evidence=list(edge.supporting_evidence),
                            type_status=STATUS_TRUE,
                            evidence_status=STATUS_TRUE,
                            constraint_status=STATUS_TRUE,
                            final_status=STATUS_TRUE,
                            explanation=(
                                "Resume the existing Step1 structural chain after "
                                "the LLM-selected mechanism."
                            ),
                        )
                    )
                next_state = SearchState(
                    signal_origin=current_state.signal_origin,
                    current_node_id=target.node_id,
                    visited_node_ids=current_state.visited_node_ids + [target.node_id],
                    path_edge_ids=current_state.path_edge_ids + [path_edge.edge_id],
                    mechanism_instances=list(current_state.mechanism_instances),
                    unknown_preconditions=list(current_state.unknown_preconditions),
                    false_preconditions=list(current_state.false_preconditions),
                    accumulated_evidence=(
                        current_state.accumulated_evidence
                        + list(edge.supporting_evidence)
                    ),
                    depth=current_state.depth,
                    path_score=self.scorer.score(current_state, edge),
                    status=ACTIVE,
                    structural_resume_node_id="",
                )
                key = tuple(next_state.visited_node_ids)
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(next_state)
                queue.append(next_state)

        if expanded:
            self.logs.append(
                {
                    "event": "structural_closure",
                    "source_state": state.to_dict(),
                    "reachable_state_count": len(expanded),
                    "reachable_node_ids": [
                        item.current_node_id for item in expanded
                    ],
                }
            )
        return expanded

    def _finalize_structural_outputs(
        self,
        closure_states: List[SearchState],
    ) -> None:
        for terminal_state in closure_states:
            node = self.graph.nodes.get(terminal_state.current_node_id)
            if node is None or node.node_type != "ComponentNode":
                continue
            if node.component_category != "Communication Interface":
                continue
            has_structural_successor = any(
                edge.edge_id.startswith("structure_")
                and not edge.mechanism_name
                and edge.final_status == STATUS_TRUE
                for edge in self.graph.outgoing(node.node_id)
            )
            if has_structural_successor:
                continue
            candidate = {
                "source_node_id": node.node_id,
                "proposed_target": {
                    "node_type": "ObservableOutputNode",
                    "name": self._observable_output_name(),
                    "modality": "digital",
                    "component_category": node.component_category,
                    "component_name": node.component_name or node.name,
                },
                "relation_type": "observe",
                "mechanism_name": None,
                "input_modality": node.modality or "digital",
                "plain_language_explanation": (
                    "The LLM-selected mechanism reaches the known sensor readout "
                    "through existing Step1 structural edges."
                ),
            }
            result = self._apply_candidate(terminal_state, candidate)
            self.logs.append(
                {
                    "event": "structural_output_finalization",
                    "source_node_id": node.node_id,
                    "status": result.status if result is not None else REJECTED,
                }
            )

    def _mechanism_followup_frontier(
        self,
        source_state: SearchState,
        closure_states: List[SearchState],
    ) -> List[SearchState]:
        """Let LLM reason after an accepted EM injection has entered the signal chain."""
        if not self._is_em_injection_state(source_state):
            return []

        followups: List[SearchState] = []
        seen_targets: Set[str] = set()
        for state in [source_state] + list(closure_states):
            for target in self._electrical_signal_chain_resume_targets(state):
                if target.node_id in state.visited_node_ids or target.node_id in seen_targets:
                    continue
                seen_targets.add(target.node_id)
                edge = self.graph.add_edge(
                    GraphEdge(
                        edge_id=self.graph.next_edge_id("injection_resume"),
                        source_node_id=state.current_node_id,
                        target_node_id=target.node_id,
                        relation_type="propagate",
                        attack_origin=state.signal_origin,
                        input_modality=(
                            self.graph.nodes[state.current_node_id].modality
                            or "electrical"
                        ),
                        output_modality=target.modality or "electrical",
                        supporting_evidence=list(target.evidence_refs),
                        type_status=STATUS_TRUE,
                        evidence_status=STATUS_TRUE,
                        constraint_status=STATUS_TRUE,
                        final_status=STATUS_TRUE,
                        explanation=(
                            "Continue graph search from the LLM-validated "
                            "electromagnetic injection point into the existing "
                            "sensor signal chain."
                        ),
                    )
                )
                followups.append(
                    SearchState(
                        signal_origin=state.signal_origin,
                        current_node_id=target.node_id,
                        visited_node_ids=state.visited_node_ids + [target.node_id],
                        path_edge_ids=state.path_edge_ids + [edge.edge_id],
                        mechanism_instances=list(state.mechanism_instances),
                        unknown_preconditions=list(state.unknown_preconditions),
                        false_preconditions=list(state.false_preconditions),
                        accumulated_evidence=(
                            state.accumulated_evidence + list(target.evidence_refs)
                        ),
                        depth=state.depth + 1,
                        path_score=self.scorer.score(state, edge),
                        status=ACTIVE,
                    )
                )

        if followups:
            self.logs.append(
                {
                    "event": "mechanism_followup_frontier",
                    "source_state": source_state.to_dict(),
                    "followup_node_ids": [state.current_node_id for state in followups],
                    "reason": (
                        "EM-induced electrical disturbance is handed back to LLM "
                        "at existing AFE/ADC signal-chain nodes."
                    ),
                }
            )
        return followups

    def _is_em_injection_state(self, state: SearchState) -> bool:
        if state.signal_origin != "electromagnetic":
            return False
        node = self.graph.nodes.get(state.current_node_id)
        if node is None:
            return False
        if node.component_category not in {"Wires", "Power Supply", "Communication Interface"}:
            return False
        return any(
            item.mechanism_name == "Antenna Effect"
            for item in state.mechanism_instances
        )

    def _electrical_signal_chain_resume_targets(self, state: SearchState) -> List[GraphNode]:
        target_categories = ["Amplifier", "Signal Conditioning Circuits", "ADC"]
        order = {category: index for index, category in enumerate(target_categories)}
        candidates = [
            node
            for node in self.graph.component_nodes()
            if node.component_category in order
            and node.evidence_status == STATUS_TRUE
        ]
        candidates.sort(
            key=lambda node: (
                order[node.component_category],
                0 if node.source_stage == "step1" else 1,
                node.node_id,
            )
        )
        return candidates

    def _observable_output_name(self) -> str:
        text = self.graph.sensor_model.lower()
        components = " ".join(
            node.name.lower() for node in self.graph.component_nodes()
        )
        joined = f"{text} {components}"
        if any(key in joined for key in ["microphone", "digital audio", "i2s", "i²s"]):
            return "distorted digital audio output"
        if any(key in joined for key in ["rgb", "color", "clear photodiode"]):
            return "abnormal RGB/Clear color intensity"
        if any(key in joined for key in ["ccd", "camera", "video"]):
            return "distorted electrical video output"
        if any(key in joined for key in ["accelerometer", "acceleration"]):
            return "false acceleration"
        if any(key in joined for key in ["gyro", "angular"]):
            return "false angular velocity"
        if any(key in joined for key in ["distance", "ultrasonic"]):
            return "abnormal distance"
        return "other target-specific digital anomaly"

    def _mechanism_signature(self, state: SearchState) -> Tuple[Tuple[str, str], ...]:
        return tuple(
            (item.mechanism_name, item.source_component.strip().lower())
            for item in state.mechanism_instances
        )

    def _state_analysis_key(self, state: SearchState) -> Tuple[Any, ...]:
        return (
            state.signal_origin,
            state.current_node_id,
            self._mechanism_signature(state),
        )

    def _expansion_task_for_state(self, state: SearchState) -> str:
        node = self.graph.nodes.get(state.current_node_id)
        if node is None:
            return "structure_completion_expansion"
        if node.node_type == "ExternalSignalNode":
            return "entry_expansion"
        if node.node_type in {"ComponentNode", "BoundaryNode"}:
            return "component_mechanism_expansion"
        if node.node_type == "SignalStateNode":
            return "signal_propagation_expansion"
        return "signal_propagation_expansion"

    def _frontier_query_key(self, state: SearchState) -> Tuple[Any, ...]:
        node = self.graph.nodes.get(state.current_node_id)
        expansion_task = self._expansion_task_for_state(state)
        if node and expansion_task == "component_mechanism_expansion":
            return (
                state.signal_origin,
                expansion_task,
                node.node_type,
                node.component_category,
                node.modality,
                "has_mechanism" if state.mechanism_instances else "no_mechanism",
            )
        return (
            state.signal_origin,
            state.current_node_id,
            expansion_task,
            "has_mechanism" if state.mechanism_instances else "no_mechanism",
            node.node_type if node else "",
            node.component_category if node else "",
            node.modality if node else "",
        )

    def _group_frontier_queries(
        self,
        frontier: List[SearchState],
        layer_index: int,
    ) -> Tuple[List[Tuple[str, SearchState]], Dict[str, List[Tuple[str, SearchState]]]]:
        by_query_key: Dict[Tuple[Any, ...], List[Tuple[str, SearchState]]] = {}
        for state_index, state in enumerate(frontier):
            state_id = f"layer_{layer_index}_state_{state_index}"
            by_query_key.setdefault(self._frontier_query_key(state), []).append((state_id, state))

        query_batch: List[Tuple[str, SearchState]] = []
        query_groups: Dict[str, List[Tuple[str, SearchState]]] = {}
        for query_index, (_query_key, members) in enumerate(by_query_key.items()):
            query_id = f"layer_{layer_index}_query_{query_index}"
            representative = max(members, key=lambda item: item[1].path_score)[1]
            query_batch.append((query_id, representative))
            query_groups[query_id] = members
        return query_batch, query_groups

    def _rebind_candidate_to_member(
        self,
        candidate: Dict[str, Any],
        representative_state: SearchState,
        member_state: SearchState,
    ) -> Dict[str, Any]:
        if representative_state.current_node_id == member_state.current_node_id:
            return candidate
        rebound = dict(candidate)
        rebound["source_node_id"] = member_state.current_node_id
        target = dict(candidate.get("proposed_target") or {})
        representative_node = self.graph.nodes.get(representative_state.current_node_id)
        member_node = self.graph.nodes.get(member_state.current_node_id)
        if representative_node is None or member_node is None:
            rebound["proposed_target"] = target
            return rebound

        target_type = target.get("node_type")
        target_names = {
            str(target.get("name") or "").strip().lower(),
            str(target.get("component_name") or "").strip().lower(),
        }
        representative_names = {
            str(representative_node.name or "").strip().lower(),
            str(representative_node.component_name or "").strip().lower(),
        }
        targets_representative = bool(target_names & representative_names)
        if target_type in {"SignalStateNode", "ObservableOutputNode"}:
            target["component_category"] = member_node.component_category
            target["component_name"] = member_node.component_name or member_node.name
            name = str(target.get("name") or "")
            for old in [representative_node.component_name, representative_node.name]:
                if old and old in name:
                    name = name.replace(old, member_node.component_name or member_node.name)
            target["name"] = name
        elif target_type in {"ComponentNode", "BoundaryNode"} and targets_representative:
            target.update(
                {
                    "node_type": member_node.node_type,
                    "name": member_node.name,
                    "modality": member_node.modality,
                    "component_category": member_node.component_category,
                    "component_name": member_node.component_name or member_node.name,
                }
            )
        rebound["proposed_target"] = target
        return rebound

    def _prune_frontier(self, frontier: List[SearchState]) -> List[SearchState]:
        by_signal: Dict[str, List[SearchState]] = {}
        for state in frontier:
            by_signal.setdefault(state.signal_origin, []).append(state)

        selected: List[SearchState] = []
        for signal in SIGNAL_ORIGINS:
            states = by_signal.get(signal, [])
            states.sort(key=lambda item: (-item.path_score, item.current_node_id))
            seen = set()
            kept = 0
            for state in states:
                # Step2 discovers mechanisms, not every combination of mechanisms
                # that can precede the same component.
                key = (state.current_node_id, self._mechanism_signature(state))
                if key in seen:
                    continue
                seen.add(key)
                selected.append(state)
                kept += 1
                if kept >= self.config.beam_width:
                    break
        return selected

    def _apply_candidate(self, state: SearchState, candidate: Dict[str, Any]) -> Optional[SearchState]:
        source_id = candidate.get("source_node_id") or state.current_node_id
        if source_id != state.current_node_id or source_id not in self.graph.nodes:
            self._record_rejected(state, candidate, "candidate source_node_id does not match current state")
            return None
        source_node = self.graph.nodes[source_id]

        schema_error = self._validate_schema(candidate)
        if schema_error:
            self._record_rejected(state, candidate, schema_error)
            return None

        target_node, target_error = self._get_or_create_target_node(candidate)
        if target_error:
            self._record_rejected(state, candidate, target_error)
            return None

        if target_node.node_id in state.visited_node_ids:
            self._record_rejected(state, candidate, "cycle validation failed")
            return None

        mechanism_name = canonical_mechanism(candidate.get("mechanism_name"))
        relation_type = candidate.get("relation_type")
        if relation_type == "apply" and not mechanism_name:
            self._record_rejected(state, candidate, "apply edge requires one of the eight allowed mechanisms")
            return None
        if mechanism_name:
            mechanism_component = (
                target_node.component_name
                or target_node.name
                or source_node.component_name
                or source_node.name
            ).strip().lower()
            if any(
                item.mechanism_name == mechanism_name
                and item.source_component.strip().lower() == mechanism_component
                for item in state.mechanism_instances
            ):
                self._record_rejected(
                    state,
                    candidate,
                    "duplicate mechanism on the same component and signal path",
                )
                return None

        edge = GraphEdge(
            edge_id=self.graph.next_edge_id("search"),
            source_node_id=source_node.node_id,
            target_node_id=target_node.node_id,
            relation_type=relation_type,
            mechanism_name=mechanism_name or None,
            attack_origin=state.signal_origin,
            input_modality=candidate.get("input_modality") or source_node.modality or state.signal_origin,
            output_modality=target_node.modality or candidate.get("output_modality") or source_node.modality,
            mandatory_preconditions=list(candidate.get("mandatory_preconditions") or []),
            parameter_constraints=list(candidate.get("parameter_constraints") or []),
            supporting_evidence=list(target_node.evidence_refs),
            explanation=candidate.get("plain_language_explanation", ""),
        )
        if target_node.evidence_status != STATUS_TRUE:
            edge.mandatory_preconditions.append(
                {
                    "claim": f"Target node is admissible: {target_node.name}",
                    "required_evidence_scope": "target_specific",
                    "current_status": target_node.evidence_status,
                    "evidence_refs": list(target_node.evidence_refs),
                }
            )

        if mechanism_name:
            check_result = self.registry.check(mechanism_name, self.graph, source_node, target_node, candidate)
            edge.type_status = check_result.status
            edge.mandatory_preconditions.extend(check_result.mandatory_preconditions)
            edge.parameter_constraints.extend(check_result.parameter_constraints)
            if check_result.status == STATUS_FALSE:
                edge.evidence_status = self.evidence_checker.check_preconditions(edge.mandatory_preconditions)
                edge.constraint_status = self.constraint_checker.check(edge.parameter_constraints)
                edge.final_status = STATUS_FALSE
                self.graph.add_edge(edge)
                rejected = self._path_from_state(
                    state,
                    status=REJECTED,
                    extra_edge=edge,
                    observable_output="",
                    rejection_reason=check_result.explanation,
                )
                self.rejected_paths.append(rejected)
                self.logs.append({"event": "pruned_edge", "candidate": candidate, "edge": edge.to_dict(), "reason": check_result.explanation})
                return None
        else:
            edge.type_status = STATUS_TRUE

        edge.evidence_status = self.evidence_checker.check_preconditions(edge.mandatory_preconditions)
        edge.constraint_status = self.constraint_checker.check(edge.parameter_constraints)
        edge.final_status = self._merge_status(edge.type_status, edge.evidence_status, edge.constraint_status)
        self.graph.add_edge(edge)

        new_instances = list(state.mechanism_instances)
        if mechanism_name:
            new_instances.append(
                MechanismInstance(
                    mechanism_name=mechanism_name,
                    source_component=target_node.component_name or source_node.component_name or target_node.name or source_node.name,
                    mechanism_node_id=f"edge:{edge.edge_id}",
                    plain_language_analysis=edge.explanation,
                    evidence_refs=list(edge.supporting_evidence),
                )
            )

        new_unknowns = list(state.unknown_preconditions)
        for precondition in edge.mandatory_preconditions:
            if precondition.get("current_status") == STATUS_UNKNOWN:
                new_unknowns.append(precondition)

        new_false = list(state.false_preconditions)
        for precondition in edge.mandatory_preconditions:
            if precondition.get("current_status") == STATUS_FALSE:
                new_false.append(precondition)

        if edge.final_status == STATUS_FALSE:
            rejected = self._path_from_state(state, REJECTED, edge, "", "edge final_status is FALSE")
            self.rejected_paths.append(rejected)
            self.logs.append({"event": "pruned_edge", "candidate": candidate, "edge": edge.to_dict(), "reason": "edge final_status is FALSE"})
            return None

        new_state = SearchState(
            signal_origin=state.signal_origin,
            current_node_id=target_node.node_id,
            visited_node_ids=state.visited_node_ids + [target_node.node_id],
            path_edge_ids=state.path_edge_ids + [edge.edge_id],
            mechanism_instances=new_instances,
            unknown_preconditions=new_unknowns,
            false_preconditions=new_false,
            accumulated_evidence=state.accumulated_evidence + list(edge.supporting_evidence),
            depth=state.depth + 1,
            path_score=self.scorer.score(state, edge),
            status=ACTIVE,
            structural_resume_node_id=(
                source_node.node_id
                if mechanism_name
                and source_node.node_type in {"ComponentNode", "BoundaryNode"}
                and target_node.node_type == "SignalStateNode"
                else ""
            ),
        )

        if target_node.node_type == "ObservableOutputNode":
            if new_instances and edge.final_status == STATUS_TRUE and not new_false and not new_unknowns:
                new_state.status = ACCEPTED
                path = self._path_from_state(new_state, ACCEPTED, None, target_node.name, "")
                self.accepted_paths.append(path)
                self.logs.append({"event": "accepted_path", "path_id": path.path_id, "mechanisms": [item.to_dict() for item in new_instances]})
            else:
                new_state.status = UNRESOLVED
                path = self._path_from_state(new_state, UNRESOLVED, None, target_node.name, "observable reached with UNKNOWN or missing mechanism")
                self.unresolved_paths.append(path)
                self.logs.append({"event": "unknown_edge", "path_id": path.path_id, "reason": path.rejection_reason})
            return new_state

        if edge.final_status == STATUS_UNKNOWN or len(new_unknowns) > self.config.max_unknown_edges:
            path = self._path_from_state(new_state, UNRESOLVED, None, "", "UNKNOWN preconditions remain")
            self.unresolved_paths.append(path)
            self.logs.append({"event": "unknown_edge", "edge": edge.to_dict(), "reason": "UNKNOWN preconditions remain"})
            if len(new_unknowns) > self.config.max_unknown_edges:
                return None

        self.logs.append({"event": "accepted_edge", "edge": edge.to_dict(), "state": new_state.to_dict()})
        return new_state

    def _validate_schema(self, candidate: Dict[str, Any]) -> str:
        if not isinstance(candidate, dict):
            return "candidate is not a JSON object"
        target = candidate.get("proposed_target")
        if not isinstance(target, dict):
            return "candidate missing proposed_target object"
        if target.get("node_type") not in {"BoundaryNode", "ComponentNode", "SignalStateNode", "ObservableOutputNode"}:
            return "invalid proposed_target.node_type"
        relation_type = candidate.get("relation_type")
        if relation_type != "apply" and relation_type not in NORMAL_RELATIONS:
            return "invalid relation_type"
        mechanism = candidate.get("mechanism_name")
        if mechanism not in (None, "", "null") and canonical_mechanism(mechanism) not in ALLOWED_MECHANISMS:
            return f"mechanism taxonomy validation failed: {mechanism}"
        return ""

    def _get_or_create_target_node(self, candidate: Dict[str, Any]) -> Tuple[Optional[GraphNode], str]:
        target = candidate["proposed_target"]
        node_type = target.get("node_type")
        name = str(target.get("name") or "").strip()
        component_name = str(target.get("component_name") or "").strip()
        if not name:
            return None, "target node name is empty"
        if node_type in {"ComponentNode", "BoundaryNode"}:
            existing = self.graph.find_node(node_type=node_type, name=name, component_name=component_name)
            if existing:
                return existing, ""
            existing = self._find_existing_structural_target(node_type, name, component_name)
            if existing:
                return existing, ""
            return (
                None,
                "LLM search may not create new ComponentNode/BoundaryNode targets; "
                "the ordered architecture graph must be supplied by Step1 or expert knowledge before search.",
            )
        existing = self.graph.find_node(node_type=node_type, name=name, component_name=component_name, modality=target.get("modality") or "")
        if existing:
            return existing, ""
        evidence_status = self.graph.component_evidence_status(component_name)
        node = self.graph.add_node(
            GraphNode(
                node_id=self.graph.next_node_id("search_node"),
                node_type=node_type,
                name=name,
                modality=target.get("modality") or "",
                component_category=target.get("component_category") or "",
                component_name=component_name,
                evidence_status=evidence_status,
                source_stage="search_generated",
            )
        )
        return node, ""

    def _find_existing_structural_target(self, node_type: str, name: str, component_name: str) -> Optional[GraphNode]:
        wanted_names = {
            value.strip().lower()
            for value in [name, component_name]
            if value and value.strip()
        }
        if not wanted_names:
            return None
        for node in self.graph.nodes.values():
            if node.node_type not in {"ComponentNode", "BoundaryNode"}:
                continue
            node_names = {
                value.strip().lower()
                for value in [node.name, node.component_name, *node.attributes.get("collapsed_aliases", [])]
                if value and value.strip()
            }
            if wanted_names & node_names:
                return node
        return None

    def _merge_status(self, *statuses: str) -> str:
        if STATUS_FALSE in statuses:
            return STATUS_FALSE
        if STATUS_UNKNOWN in statuses:
            return STATUS_UNKNOWN
        return STATUS_TRUE

    def _record_rejected(self, state: SearchState, candidate: Dict[str, Any], reason: str) -> None:
        self.logs.append({"event": "pruned_edge", "state": state.to_dict(), "candidate": candidate, "reason": reason})
        self.rejected_paths.append(self._path_from_state(state, REJECTED, None, "", reason))

    def _record_unresolved(self, state: SearchState, reason: str) -> None:
        self.logs.append({"event": "unknown_edge", "state": state.to_dict(), "reason": reason})
        self.unresolved_paths.append(self._path_from_state(state, UNRESOLVED, None, "", reason))

    def _path_from_state(
        self,
        state: SearchState,
        status: str,
        extra_edge: Optional[GraphEdge],
        observable_output: str,
        rejection_reason: str,
    ) -> MechanismPath:
        edge_ids = list(state.path_edge_ids)
        if extra_edge is not None:
            edge_ids.append(extra_edge.edge_id)
        edges = [self.graph.edges[eid] for eid in edge_ids if eid in self.graph.edges]
        node_ids: List[str] = []
        for edge in edges:
            node_ids.extend([edge.source_node_id, edge.target_node_id])
        node_ids.extend(state.visited_node_ids)
        for instance in state.mechanism_instances:
            node_ids.append(instance.mechanism_node_id)
        seen: Set[str] = set()
        nodes = []
        for node_id in node_ids:
            if node_id in self.graph.nodes and node_id not in seen:
                seen.add(node_id)
                nodes.append(self.graph.nodes[node_id])
        component_categories = {
            node.component_category
            for node in nodes
            if node.component_category
        }
        relevant_parameters = parameters_for_path(
            self.graph.sensor_parameters.values(),
            component_categories,
            state.signal_origin,
        )
        path_id = f"path_{len(self.accepted_paths) + len(self.unresolved_paths) + len(self.rejected_paths) + 1}"
        return MechanismPath(
            path_id=path_id,
            status=status,
            external_signal={
                "modality": state.signal_origin,
                "description": f"external {state.signal_origin} signal",
            },
            nodes=nodes,
            edges=edges,
            mechanism_instances=list(state.mechanism_instances),
            observable_output=observable_output,
            mandatory_preconditions=[pre for edge in edges for pre in edge.mandatory_preconditions],
            unknown_preconditions=list(state.unknown_preconditions),
            counter_evidence=[],
            relevant_parameter_refs=[
                str(parameter.get("parameter_id")) for parameter in relevant_parameters
            ],
            relevant_sensor_parameters=relevant_parameters,
            path_score=state.path_score,
            rejection_reason=rejection_reason,
        )

    def _deduplicate(self) -> None:
        if not self.config.deduplicate_paths:
            return
        accepted = self._dedupe_paths(self.accepted_paths)
        accepted_by_signal: Dict[str, int] = {}
        limited_accepted: List[MechanismPath] = []
        for path in accepted:
            signal = path.external_signal.get("modality", "")
            if accepted_by_signal.get(signal, 0) >= self.config.max_paths_per_signal:
                continue
            accepted_by_signal[signal] = accepted_by_signal.get(signal, 0) + 1
            limited_accepted.append(path)
            if len(limited_accepted) >= self.config.accepted_path_limit:
                break
        self.accepted_paths = limited_accepted
        self.unresolved_paths = self._dedupe_paths(self.unresolved_paths)
        self.rejected_paths = self._dedupe_paths(self.rejected_paths)

    def _dedupe_paths(self, paths: List[MechanismPath]) -> List[MechanismPath]:
        seen = set()
        result = []
        for path in paths:
            key = (
                path.status,
                path.external_signal.get("modality"),
                tuple((item.mechanism_name, item.source_component) for item in path.mechanism_instances),
                path.observable_output,
                path.rejection_reason,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    def _result(self) -> Dict[str, Any]:
        self._deduplicate()
        payload = {
            "sensor_model": self.graph.sensor_model,
            "mechanism_taxonomy_version": "prompt3_1",
            "allowed_mechanisms": ALLOWED_MECHANISMS,
            "signal_coverage": dict(self.signal_coverage),
            "attack_scope": self.scope_policy.metadata(),
            "graph_summary": self.graph.summary(),
            "sensor_parameter_catalog": list(self.graph.sensor_parameters.values()),
            "accepted_paths": [path.to_dict() for path in self.accepted_paths],
            "unresolved_paths": [path.to_dict() for path in self.unresolved_paths],
            "rejected_paths": [path.to_dict() for path in self.rejected_paths],
            "search_statistics": {
                "accepted_count": len(self.accepted_paths),
                "unresolved_count": len(self.unresolved_paths),
                "rejected_count": len(self.rejected_paths),
                "llm_expansions": self.llm_expansions,
                "llm_layer_calls": self.llm_expansions,
                "log_count": len(self.logs),
            },
            "search_log": self.logs,
        }
        # Path adjudication is authoritative: rejected branches are retained
        # for audit only and must never leak local edges into Step2 output.
        payload["mechanism_candidates"] = (
            collect_surviving_path_mechanism_candidates(payload)
        )
        return payload
