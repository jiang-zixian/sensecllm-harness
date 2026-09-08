from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from sensecllm.harness.state import RunState, RunStatus
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.models.chatanywhere import ChatAnywhereGateway

EvidenceRetriever = Callable[[str], list[dict[str, Any]]]


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.casefold() in {"1", "true", "yes", "on"}
    return default


def _limit(value: Any, max_chars: int = 6000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return text[:max_chars]


class PostAnalysisChatService:
    """Post-analysis chat agent over one completed or in-progress run.

    The main analysis workflow remains deterministic. Once artifacts exist, this
    service lets an LLM plan a bounded evidence-gathering step over run
    artifacts, conversation history, episodic memory, and optional RAG.
    """

    def __init__(
        self,
        memory: EpisodicMemoryStore,
        *,
        rag_retriever: EvidenceRetriever | None = None,
        max_planning_rounds: int = 2,
    ) -> None:
        self.memory = memory
        self.rag_retriever = rag_retriever or self._retrieve_rag_evidence
        self.max_planning_rounds = max(1, min(max_planning_rounds, 4))

    @staticmethod
    def _chunks(state: RunState) -> list[dict[str, str]]:
        paths = [Path(state.report_path)]
        paths.extend(sorted(state.data_dir.glob("*.json")))
        chunks: list[dict[str, str]] = []
        for path in paths:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for index in range(0, len(text), 4000):
                value = text[index : index + 4000].strip()
                if value:
                    chunks.append({"source": path.name, "chunk": str(index // 4000), "content": value})
        return chunks

    @staticmethod
    def _retrieve(question: str, chunks: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
        terms = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", question.casefold()))
        ranked = sorted(
            chunks,
            key=lambda item: sum(term in item["content"].casefold() for term in terms),
            reverse=True,
        )
        return ranked[:limit]

    @staticmethod
    def _heuristic_plan(question: str, state: RunState) -> dict[str, Any]:
        lowered = question.casefold()
        asks_memory = any(term in lowered for term in ("memory", "history", "similar", "历史", "案例", "相似"))
        asks_rag = any(
            term in lowered
            for term in ("rag", "paper", "citation", "evidence", "论文", "文献", "证据", "来源")
        )
        asks_web = any(
            term in lowered
            for term in ("web", "internet", "online", "latest", "网络", "网上", "最新", "新闻")
        )
        asks_critic = any(
            term in lowered
            for term in ("risk", "check", "verify", "credible", "critic", "风险", "审查", "可信", "充分")
        )
        return {
            "intent": "post_analysis_follow_up",
            "needs_artifacts": True,
            "needs_conversation": True,
            "needs_memory": asks_memory,
            "needs_rag": asks_rag or asks_web,
            "needs_web": asks_web,
            "needs_critic": asks_critic,
            "answer_style": "concise",
            "reason": (
                "Heuristic fallback plan; run is completed."
                if state.status == RunStatus.COMPLETED
                else "Heuristic fallback plan; run is not completed yet, so available artifacts may be partial."
            ),
        }

    def _plan(self, state: RunState, question: str, gateway: ChatAnywhereGateway) -> dict[str, Any]:
        if not gateway.available:
            return self._heuristic_plan(question, state)
        try:
            response = gateway.complete_json(
                model=state.model,
                system_prompt=(
                    "You are the planner for a post-analysis chat agent. The main analysis "
                    "pipeline has already produced or is producing artifacts. Return only JSON "
                    "with these keys: intent, needs_artifacts, needs_conversation, needs_memory, "
                    "needs_rag, needs_web, needs_critic, answer_style, reason. Choose a bounded "
                    "evidence plan; do not propose rerunning the main workflow unless the user asks."
                ),
                user_prompt=json.dumps(
                    {
                        "run_status": state.status.value,
                        "available_artifacts": sorted(state.artifacts),
                        "question": question,
                    },
                    ensure_ascii=False,
                ),
            )
        except (RuntimeError, TypeError, ValueError, json.JSONDecodeError, requests.RequestException):
            return self._heuristic_plan(question, state)
        plan = self._heuristic_plan(question, state)
        for key in (
            "intent",
            "needs_artifacts",
            "needs_conversation",
            "needs_memory",
            "needs_rag",
            "needs_web",
            "needs_critic",
            "answer_style",
            "reason",
        ):
            if key in response:
                plan[key] = response[key]
        for key in ("needs_artifacts", "needs_conversation", "needs_memory", "needs_rag", "needs_web", "needs_critic"):
            plan[key] = _as_bool(plan.get(key), default=bool(plan.get(key)))
        # The chat layer must stay grounded in run outputs; never let the planner disable artifacts.
        plan["needs_artifacts"] = True
        return plan

    def _replan(
        self,
        state: RunState,
        question: str,
        gateway: ChatAnywhereGateway,
        prior_plan: dict[str, Any],
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        fallback = dict(prior_plan)
        fallback["needs_artifacts"] = True
        if not observation.get("evidence_count"):
            fallback["needs_memory"] = True
            fallback["needs_rag"] = True
        if "rag" in observation.get("missing_sources", []):
            fallback["needs_rag"] = True
        if "web" in observation.get("missing_sources", []):
            fallback["needs_web"] = True
            fallback["needs_rag"] = True
        fallback["reason"] = f"Replan after observation: {observation.get('reason', '')}"
        if not gateway.available:
            return fallback
        try:
            response = gateway.complete_json(
                model=state.model,
                system_prompt=(
                    "You are replanning a bounded post-analysis chat step after observing the "
                    "first evidence-gathering result. Return only JSON with keys: intent, "
                    "needs_artifacts, needs_conversation, needs_memory, needs_rag, needs_web, "
                    "needs_critic, answer_style, reason. Prefer adding missing evidence sources; "
                    "do not rerun the main analysis workflow."
                ),
                user_prompt=json.dumps(
                    {
                        "question": question,
                        "run_status": state.status.value,
                        "prior_plan": prior_plan,
                        "observation": observation,
                    },
                    ensure_ascii=False,
                ),
            )
        except (RuntimeError, TypeError, ValueError, json.JSONDecodeError, requests.RequestException):
            return fallback
        for key in (
            "intent",
            "needs_artifacts",
            "needs_conversation",
            "needs_memory",
            "needs_rag",
            "needs_web",
            "needs_critic",
            "answer_style",
            "reason",
        ):
            if key in response:
                fallback[key] = response[key]
        for key in (
            "needs_artifacts",
            "needs_conversation",
            "needs_memory",
            "needs_rag",
            "needs_web",
            "needs_critic",
        ):
            fallback[key] = _as_bool(fallback.get(key), default=bool(fallback.get(key)))
        fallback["needs_artifacts"] = True
        return fallback

    def _artifact_evidence(self, state: RunState, question: str) -> list[dict[str, Any]]:
        return [
            {
                "source_type": "artifact",
                "source": item["source"],
                "chunk": item["chunk"],
                "content": item["content"],
            }
            for item in self._retrieve(question, self._chunks(state))
        ]

    def _conversation_evidence(self, run_id: str) -> list[dict[str, Any]]:
        messages = self.memory.list_messages(run_id, limit=12)
        evidence: list[dict[str, Any]] = []
        for index, message in enumerate(messages[-8:]):
            evidence.append(
                {
                    "source_type": "conversation",
                    "source": "conversation_messages",
                    "chunk": str(index),
                    "content": f"{message['role']}: {_limit(message['content'], 1000)}",
                }
            )
        return evidence

    def _memory_evidence(self, state: RunState, question: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        case_id = str(state.metadata.get("episodic_case_id") or "")
        if case_id:
            case = self.memory.get_case(case_id)
            if case:
                evidence.append(
                    {
                        "source_type": "memory",
                        "source": "episodic_case",
                        "chunk": case_id,
                        "content": _limit(case, 5000),
                    }
                )
        for case in self.memory.search_cases(question, limit=4):
            if str(case.get("id")) == case_id:
                continue
            evidence.append(
                {
                    "source_type": "memory",
                    "source": "similar_cases",
                    "chunk": str(case.get("id") or ""),
                    "content": _limit(case, 2000),
                }
            )
        return evidence[:5]

    @staticmethod
    def _retrieve_rag_evidence(question: str) -> list[dict[str, Any]]:
        endpoint = os.getenv("SENSECLLM_RAG_RETRIEVE_URL", "http://127.0.0.1:8001/v1/retrieve")
        try:
            response = requests.post(
                endpoint,
                json={
                    "query": question,
                    "inputs": {
                        "RAGinput": question,
                        "mode": "evidence",
                    },
                    "response_mode": "blocking",
                },
                timeout=float(os.getenv("SENSECLLM_POST_ANALYSIS_RAG_TIMEOUT", "20")),
            )
            if response.status_code != 200:
                return []
            payload = response.json()
        except (RuntimeError, TypeError, ValueError, json.JSONDecodeError, requests.RequestException):
            return []

        evidence = []
        content = str(payload.get("evidence") or payload.get("answer") or "").strip()
        if content:
            evidence.append(
                {
                    "source_type": "rag",
                    "source": "sensor_rag",
                    "chunk": "evidence",
                    "content": content[:12_000],
                }
            )
        for index, item in enumerate(payload.get("sources") or []):
            evidence.append(
                {
                    "source_type": "paper",
                    "source": str(item.get("title") or item.get("source_path") or "paper_source"),
                    "chunk": str(item.get("chunk_id") or index),
                    "content": _limit(item, 2000),
                }
            )
        for index, item in enumerate(payload.get("web_sources") or []):
            evidence.append(
                {
                    "source_type": "web",
                    "source": str(item.get("url") or item.get("provider") or "web_source"),
                    "chunk": str(item.get("rank") or index),
                    "content": _limit(item, 2000),
                }
            )
        return evidence[:10]

    @staticmethod
    def _dedupe_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for item in evidence:
            key = (
                str(item.get("source_type") or ""),
                str(item.get("source") or ""),
                str(item.get("chunk") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _execute_plan(
        self,
        state: RunState,
        question: str,
        plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        if _as_bool(plan.get("needs_artifacts"), True):
            evidence.extend(self._artifact_evidence(state, question))
        if _as_bool(plan.get("needs_conversation"), True):
            evidence.extend(self._conversation_evidence(state.run_id))
        if _as_bool(plan.get("needs_memory"), False):
            evidence.extend(self._memory_evidence(state, question))
        if _as_bool(plan.get("needs_rag"), False) or _as_bool(plan.get("needs_web"), False):
            evidence.extend(self.rag_retriever(question))
        return self._dedupe_evidence(evidence)

    @staticmethod
    def _observe(plan: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
        source_types = sorted({str(item.get("source_type") or "") for item in evidence})
        available_sources = set(source_types)
        missing_sources: list[str] = []
        if _as_bool(plan.get("needs_rag"), False) and not (
            {"rag", "paper", "web"} & available_sources
        ):
            missing_sources.append("rag")
        if _as_bool(plan.get("needs_web"), False) and "web" not in available_sources:
            missing_sources.append("web")
        if _as_bool(plan.get("needs_memory"), False) and "memory" not in available_sources:
            missing_sources.append("memory")
        should_replan = not evidence or bool(missing_sources)
        if not evidence:
            reason = "No evidence gathered."
        elif missing_sources:
            reason = f"Missing requested evidence sources: {', '.join(missing_sources)}."
        else:
            reason = "Evidence plan satisfied."
        return {
            "evidence_count": len(evidence),
            "source_types": source_types,
            "missing_sources": missing_sources,
            "should_replan": should_replan,
            "reason": reason,
        }

    @staticmethod
    def _citations(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [
            {
                "source_type": str(item["source_type"]),
                "source": str(item["source"]),
                "chunk": str(item["chunk"]),
            }
            for item in evidence
        ]

    def ask(self, state: RunState, question: str) -> dict[str, Any]:
        self.memory.add_message(state.run_id, "user", question)
        gateway = ChatAnywhereGateway(usage_file=Path(state.run_dir) / "usage.jsonl")
        plan = self._plan(state, question, gateway)
        plans = [plan]
        observations: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for round_index in range(self.max_planning_rounds):
            evidence = self._execute_plan(state, question, plan)
            observation = self._observe(plan, evidence)
            observation["round"] = round_index + 1
            observations.append(observation)
            if not observation["should_replan"] or round_index + 1 >= self.max_planning_rounds:
                break
            plan = self._replan(state, question, gateway, plan, observation)
            plans.append(plan)

        citations = self._citations(evidence)
        if gateway.available and evidence:
            response = gateway.complete_json(
                model=state.model,
                system_prompt=(
                    "You are a post-analysis assistant for a sensor-security run. Answer using only "
                    "the supplied evidence from run artifacts, conversation history, episodic memory, "
                    "paper RAG, and web snippets. Treat memory as prior and web snippets as timely "
                    "background, not proof. If evidence is insufficient, say so. Return JSON with "
                    "answer and citations; citations must use supplied source_type/source/chunk triples."
                ),
                user_prompt=json.dumps(
                    {
                        "question": question,
                        "run_status": state.status.value,
                        "plan": plan,
                        "evidence": evidence,
                    },
                    ensure_ascii=False,
                )[:40_000],
            )
            answer = str(response.get("answer") or "现有运行产物不足以回答该问题。")
            allowed = {
                (str(item["source_type"]), str(item["source"]), str(item["chunk"]))
                for item in evidence
            }
            claimed = response.get("citations") or []
            citations = [
                item
                for item in claimed
                if isinstance(item, dict)
                and (
                    str(item.get("source_type")),
                    str(item.get("source")),
                    str(item.get("chunk")),
                )
                in allowed
            ]
        else:
            answer = (
                "未配置模型或缺少可用产物。最相关的运行证据来自："
                + "、".join(
                    f'{item["source_type"]}:{item["source"]}#{item["chunk"]}'
                    for item in evidence[:8]
                )
                if evidence
                else "现有运行产物不足以回答该问题。"
            )
        self.memory.add_message(state.run_id, "assistant", answer, citations)
        return {
            "answer": answer,
            "citations": citations,
            "plan": plan,
            "plans": plans,
            "observations": observations,
            "evidence_sources": self._citations(evidence),
            "mode": "post_analysis",
        }


ReportChatService = PostAnalysisChatService
