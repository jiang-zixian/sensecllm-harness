from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import AgentContext, BaseAgent


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _first(mapping: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


@dataclass
class CaseRecallAgent(BaseAgent):
    name: str = "case_recall"
    depends_on: tuple[str, ...] = ("document",)
    limit: int = 5

    def execute(self, context: AgentContext) -> dict[str, Any]:
        step1 = _read_json(context.state.data_dir / "step1_output.json")
        sensor_info = step1.get("sensor_info", {})
        model = _first(
            sensor_info,
            ("model", "sensor_model", "device_model", "product_model", "型号"),
        )
        sensor_type = _first(
            sensor_info,
            ("sensor_type", "type", "category", "传感器类型", "类型"),
        ) or str(step1.get("rag_input") or "")

        merged: dict[str, dict[str, Any]] = {}
        if model:
            for case in context.memory.search_cases(model, limit=self.limit):
                merged[str(case["id"])] = case
        if sensor_type:
            for case in context.memory.search_cases(sensor_type=sensor_type, limit=self.limit):
                merged.setdefault(str(case["id"]), case)

        cases = list(merged.values())[: self.limit]
        result = {
            "device_model": model,
            "sensor_type": sensor_type,
            "cases": cases,
            "case_count": len(cases),
            "evidence_policy": "historical cases are priors, not target-device evidence",
        }
        output = context.state.data_dir / "episodic_case_recall.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        context.state.metadata["similar_cases"] = cases
        return result


@dataclass
class CaseRefinementAgent(BaseAgent):
    """Re-rank recalled episodes after current mechanisms are available."""

    name: str = "case_refinement"
    depends_on: tuple[str, ...] = ("mechanism",)
    limit: int = 5

    def execute(self, context: AgentContext) -> dict[str, Any]:
        graph = _read_json(context.state.data_dir / "step2_mechanism_paths.json")
        mechanisms: set[str] = set()
        components: set[str] = set()
        for path in graph.get("accepted_paths", []) if isinstance(graph, dict) else []:
            if not isinstance(path, dict):
                continue
            for item in path.get("mechanism_instances") or []:
                if not isinstance(item, dict):
                    continue
                mechanism = str(item.get("mechanism_name") or "").casefold()
                component = str(item.get("source_component") or "").casefold()
                if mechanism:
                    mechanisms.add(mechanism)
                if component:
                    components.add(component)

        candidates: dict[str, dict[str, Any]] = {
            str(item["id"]): item for item in context.state.metadata.get("similar_cases", [])
        }
        for mechanism in mechanisms:
            for case in context.memory.search_cases(mechanism=mechanism, limit=self.limit * 2):
                candidates.setdefault(str(case["id"]), case)

        ranked: list[dict[str, Any]] = []
        for case in candidates.values():
            detail = context.memory.get_case(str(case["id"])) or {}
            case_mechanisms = {
                str(item.get("mechanism") or "").casefold()
                for item in detail.get("findings", [])
                if item.get("mechanism")
            }
            case_components = {
                str(item.get("component") or "").casefold()
                for item in detail.get("findings", [])
                if item.get("component")
            }
            mechanism_overlap = sorted(mechanisms & case_mechanisms)
            component_overlap = sorted(components & case_components)
            confirmed = sum(
                1
                for result in detail.get("verification_results", [])
                if result.get("outcome") == "confirmed"
            )
            rejected = sum(
                1
                for result in detail.get("verification_results", [])
                if result.get("outcome") == "rejected"
            )
            inconclusive = sum(
                1
                for result in detail.get("verification_results", [])
                if result.get("outcome") == "inconclusive"
            )
            enriched = dict(case)
            enriched["memory_score"] = (
                2.0 * len(mechanism_overlap)
                + len(component_overlap)
                + 0.75 * confirmed
                - 0.75 * rejected
                - 0.1 * inconclusive
            )
            enriched["mechanism_overlap"] = mechanism_overlap
            enriched["component_overlap"] = component_overlap
            enriched["confirmed_result_count"] = confirmed
            enriched["rejected_result_count"] = rejected
            enriched["verification_signal"] = round(
                0.75 * confirmed - 0.75 * rejected - 0.1 * inconclusive, 3
            )
            ranked.append(enriched)
        ranked.sort(key=lambda item: (item["memory_score"], item["updated_at"]), reverse=True)
        ranked = ranked[: self.limit]

        result = {
            "current_mechanisms": sorted(mechanisms),
            "current_components": sorted(components),
            "cases": ranked,
            "case_count": len(ranked),
            "evidence_policy": "historical cases are priors, not target-device evidence",
        }
        output = context.state.data_dir / "episodic_case_refinement.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        context.state.metadata["similar_cases_ranked"] = ranked
        return result
