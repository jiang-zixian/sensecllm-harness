from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from sensecllm.models.chatanywhere import ChatAnywhereGateway

from .base import AgentContext, BaseAgent

CRITIC_PROMPT_VERSION = "critic-review-v2"
DETERMINISTIC_REVIEW_VERSION = "path-support-v2"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _norm_mechanism(value: Any) -> str:
    normalized = _norm(str(value or "").split(",", 1)[0])
    for suffix in ("effect", "mechanism"):
        normalized = normalized.removesuffix(suffix)
    return normalized


def _norm_component(value: Any) -> str:
    without_notes = re.sub(r"\([^)]*\)", "", str(value or ""))
    normalized = _norm(without_notes)
    aliases = {"microphone": "acoustictransducer"}
    return aliases.get(normalized, normalized)


def _canonical_vulnerabilities(items: list[Any]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        mechanism = item.get("mechanism_name") or item.get("mechanism")
        component = (
            item.get("source_component") or item.get("component") or item.get("entry_point")
        )
        name = (
            item.get("vulnerability_name")
            or item.get("title")
            or item.get("name")
            or item.get("description")
        )
        item["mechanism_name"] = str(mechanism or "")
        item["source_component"] = str(component or "")
        item["vulnerability_name"] = str(name or "")
        if not item.get("path_id") and item.get("accepted_path_ref"):
            item["path_id"] = item["accepted_path_ref"]
        canonical.append(item)
    return canonical


@dataclass
class CriticAgent(BaseAgent):
    name: str = "critic"
    depends_on: tuple[str, ...] = ("vulnerability",)

    def execute(self, context: AgentContext) -> dict[str, Any]:
        graph = _read_json(context.state.data_dir / "step2_mechanism_paths.json", {})
        vulnerabilities = _read_json(context.state.data_dir / "step3_vulnerability_items.json", [])
        deterministic = self._deterministic_review(graph, vulnerabilities)
        result: dict[str, Any] = {
            "agent": self.name,
            "prompt_version": CRITIC_PROMPT_VERSION,
            "deterministic_review_version": DETERMINISTIC_REVIEW_VERSION,
            "model": context.settings.critic_model,
            "deterministic_review": deterministic,
            "decision": deterministic["decision"],
            "requires_human_review": deterministic["decision"] != "approve",
            "llm_review": {"status": "not_required"},
        }

        gateway = ChatAnywhereGateway(usage_file=Path(context.state.run_dir) / "usage.jsonl")
        should_escalate = (
            context.settings.critic_enabled
            and deterministic["decision"] != "approve"
            and gateway.available
        )
        if should_escalate:
            try:
                review = gateway.complete_json(
                    model=context.settings.critic_model,
                    system_prompt=(
                        "You are an independent sensor-security critic. Review only the supplied "
                        "graph paths and vulnerability items. Historical cases are priors, not "
                        "target evidence. Return JSON with decision (approve, revise, reject, or "
                        "human_review), issues (array), rationale, and revised_vulnerabilities. "
                        "Only include revised_vulnerabilities when decision is revise; preserve "
                        "the source schema and never invent target evidence."
                    ),
                    user_prompt=json.dumps(
                        {
                            "deterministic_review": deterministic,
                            "accepted_paths": (graph.get("accepted_paths") or [])[:12]
                            if isinstance(graph, dict)
                            else [],
                            "vulnerabilities": vulnerabilities[:20]
                            if isinstance(vulnerabilities, list)
                            else [],
                            "similar_case_summaries": context.state.metadata.get(
                                "similar_cases_ranked",
                                context.state.metadata.get("similar_cases", []),
                            )[:5],
                        },
                        ensure_ascii=False,
                    )[:40_000],
                )
                decision = str(review.get("decision") or "human_review")
                if decision not in {"approve", "revise", "reject", "human_review"}:
                    decision = "human_review"
                result["decision"] = decision
                result["requires_human_review"] = decision != "approve"
                result["llm_review"] = {"status": "completed", **review}
                if decision == "revise":
                    revised = review.get("revised_vulnerabilities")
                    if isinstance(revised, list) and revised:
                        revised = _canonical_vulnerabilities(revised)
                        source = context.state.data_dir / "step3_vulnerability_items.json"
                        backup = context.state.data_dir / "step3_vulnerability_items.pre_critic.json"
                        if source.exists() and not backup.exists():
                            shutil.copy2(source, backup)
                        source.write_text(
                            json.dumps(revised, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        post_review = self._deterministic_review(graph, revised)
                        result["post_revision_review"] = post_review
                        result["revision_applied"] = True
                        if post_review["decision"] == "approve":
                            result["decision"] = "approve"
                            result["requires_human_review"] = False
                        else:
                            result["decision"] = "human_review"
                            result["requires_human_review"] = True
                    else:
                        result["decision"] = "human_review"
                        result["requires_human_review"] = True
                        result["revision_applied"] = False
                        result["revision_error"] = "missing revised_vulnerabilities"
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                result["llm_review"] = {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                result["decision"] = "human_review"
                result["requires_human_review"] = True
        elif deterministic["decision"] != "approve" and not gateway.available:
            result["llm_review"] = {"status": "skipped_no_api_key"}

        output = context.state.data_dir / "critic_review.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        context.state.metadata["critic_decision"] = result["decision"]
        context.state.metadata["requires_human_review"] = result["requires_human_review"]
        context.state.metadata["critic_versions"] = {
            "prompt": CRITIC_PROMPT_VERSION,
            "deterministic": DETERMINISTIC_REVIEW_VERSION,
            "model": context.settings.critic_model,
        }
        return result

    @staticmethod
    def _deterministic_review(graph: Any, vulnerabilities: Any) -> dict[str, Any]:
        accepted = graph.get("accepted_paths", []) if isinstance(graph, dict) else []
        items = vulnerabilities if isinstance(vulnerabilities, list) else []
        supported_pairs: set[tuple[str, str]] = set()
        supported_mechanisms: set[str] = set()
        for path in accepted if isinstance(accepted, list) else []:
            if not isinstance(path, dict):
                continue
            for mechanism in path.get("mechanism_instances") or []:
                if not isinstance(mechanism, dict):
                    continue
                name = _norm_mechanism(mechanism.get("mechanism_name"))
                component = _norm_component(mechanism.get("source_component"))
                if name:
                    supported_mechanisms.add(name)
                    supported_pairs.add((name, component))

        issues: list[dict[str, Any]] = []
        if not accepted:
            issues.append({"code": "no_accepted_path", "severity": "high"})
        if not items:
            issues.append({"code": "no_vulnerability_item", "severity": "high"})
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append({"code": "invalid_item", "item": index, "severity": "high"})
                continue
            mechanism = _norm_mechanism(item.get("mechanism_name"))
            component = _norm_component(item.get("source_component"))
            if not mechanism or mechanism not in supported_mechanisms:
                issues.append(
                    {"code": "mechanism_not_in_accepted_path", "item": index, "severity": "high"}
                )
            elif component and (mechanism, component) not in supported_pairs:
                issues.append(
                    {"code": "component_path_mismatch", "item": index, "severity": "medium"}
                )
            if not item.get("vulnerability_name"):
                issues.append(
                    {"code": "missing_vulnerability_name", "item": index, "severity": "medium"}
                )

        decision = "approve" if not issues else "review"
        return {
            "decision": decision,
            "issues": issues,
            "accepted_path_count": len(accepted),
            "vulnerability_count": len(items),
        }
