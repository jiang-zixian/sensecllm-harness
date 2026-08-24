from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sensecllm.harness.state import RunState
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.models.chatanywhere import ChatAnywhereGateway


class ReportChatService:
    """Small evidence-backed chat layer over artifacts from one run."""

    def __init__(self, memory: EpisodicMemoryStore) -> None:
        self.memory = memory

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
                    chunks.append(
                        {"source": path.name, "chunk": str(index // 4000), "content": value}
                    )
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

    def ask(self, state: RunState, question: str) -> dict[str, Any]:
        evidence = self._retrieve(question, self._chunks(state))
        citations = [
            {"source": item["source"], "chunk": item["chunk"]} for item in evidence
        ]
        self.memory.add_message(state.run_id, "user", question)
        gateway = ChatAnywhereGateway(usage_file=Path(state.run_dir) / "usage.jsonl")
        if gateway.available and evidence:
            response = gateway.complete_json(
                model=state.model,
                system_prompt=(
                    "Answer using only supplied run artifacts. If evidence is insufficient, say so. "
                    "Return JSON with answer and citations; citations must use supplied source/chunk pairs."
                ),
                user_prompt=json.dumps(
                    {"question": question, "evidence": evidence}, ensure_ascii=False
                )[:40_000],
            )
            answer = str(response.get("answer") or "现有运行产物不足以回答该问题。")
            allowed = {(item["source"], item["chunk"]) for item in evidence}
            claimed = response.get("citations") or []
            citations = [
                item
                for item in claimed
                if isinstance(item, dict)
                and (str(item.get("source")), str(item.get("chunk"))) in allowed
            ]
        else:
            answer = (
                "未配置模型或缺少可用产物。最相关的运行证据来自："
                + "、".join(f'{item["source"]}#{item["chunk"]}' for item in evidence)
                if evidence
                else "现有运行产物不足以回答该问题。"
            )
        self.memory.add_message(state.run_id, "assistant", answer, citations)
        return {"answer": answer, "citations": citations}
