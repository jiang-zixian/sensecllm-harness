from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import RAGConfig
from .models import SearchHit
from .query import build_retrieval_query
from .siliconflow import SiliconFlowClient
from .store import HybridStore


SYSTEM_PROMPT = """You are the evidence-grounding stage of a sensor-security analysis pipeline.
Use only the supplied paper excerpts. Produce a compact literature memo for a downstream analyst, not an uncited general answer.

Requirements:
1. Cite every technical claim with one or more source labels such as [S1].
2. Preserve concrete mechanism details when present: affected transducer/component, coupling path, waveform or frequency, distance, equipment, operating conditions, observed effect, and defenses.
3. Separate demonstrated evidence from hypotheses or transfer to a different sensor.
4. Never invent a paper, page, parameter, experiment, or result. State when evidence is insufficient.
5. Prefer directly relevant sensor signal-injection, interference, side-channel, and physical-layer security evidence.
6. Use concise headings: Direct evidence; Mechanisms and conditions; Defenses/limitations; Evidence gaps.
"""


class SensorRAG:
    def __init__(
        self,
        config: RAGConfig | None = None,
        client: SiliconFlowClient | None = None,
        store: HybridStore | None = None,
    ):
        self.config = config or RAGConfig()
        self.client = client or SiliconFlowClient(self.config)
        self.store = store or HybridStore(self.config)

    @staticmethod
    def _identifier_text(value: str) -> str:
        return "".join(char for char in value.casefold() if char.isalnum())

    @classmethod
    def _contains_excluded_term(cls, hit: SearchHit, exclude_terms: list[str]) -> bool:
        haystack = cls._identifier_text(f"{hit.title}\n{hit.source_path}\n{hit.text}")
        return any(
            normalized and normalized in haystack
            for normalized in (cls._identifier_text(term) for term in exclude_terms)
        )

    def retrieve(
        self,
        query: str,
        rag_input: str | None = None,
        exclude_terms: list[str] | None = None,
    ) -> tuple[str, list[SearchHit]]:
        retrieval_query = build_retrieval_query(query, rag_input)
        query_vector = self.client.embed([retrieval_query])[0]
        candidates = self.store.hybrid_candidates(retrieval_query, query_vector)
        if exclude_terms:
            candidates = [
                hit for hit in candidates
                if not self._contains_excluded_term(hit, exclude_terms)
            ]
        if not candidates:
            return retrieval_query, []

        rerank_docs = [
            f"Paper: {hit.title}\nPages: {hit.page_start}-{hit.page_end}\n{hit.text}"
            for hit in candidates
        ]
        ranked = self.client.rerank(retrieval_query, rerank_docs, top_n=len(candidates))
        selected: list[SearchHit] = []
        per_doc: dict[str, int] = defaultdict(int)
        for item in ranked:
            index = int(item.get("index", -1))
            if not 0 <= index < len(candidates):
                continue
            hit = candidates[index]
            hit.rerank_score = float(item.get("relevance_score", 0.0))
            if hit.rerank_score < self.config.rerank_threshold:
                continue
            if per_doc[hit.doc_id] >= self.config.max_chunks_per_paper:
                continue
            selected.append(hit)
            per_doc[hit.doc_id] += 1
            if len(selected) >= self.config.top_k:
                break
        return retrieval_query, selected

    @staticmethod
    def evidence_pack(hits: list[SearchHit]) -> str:
        if not hits:
            return "No sufficiently relevant paper evidence was retrieved from the indexed corpus."
        blocks = []
        for number, hit in enumerate(hits, start=1):
            blocks.append(
                f"{hit.citation(number)}\n"
                f"Source file: {hit.source_path}\n"
                f"Rerank score: {hit.rerank_score:.4f}\n"
                f"Excerpt:\n{hit.text}"
            )
        return "\n\n---\n\n".join(blocks)

    def answer(
        self,
        query: str,
        rag_input: str | None = None,
        evidence_only: bool = False,
        exclude_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        retrieval_query, hits = self.retrieve(query, rag_input, exclude_terms=exclude_terms)
        evidence = self.evidence_pack(hits)
        if evidence_only:
            answer = evidence
        else:
            user_task = (rag_input or query).strip()
            answer = self.client.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Sensor/task context:\n{user_task}\n\n"
                            f"Retrieved evidence:\n{evidence}\n\n"
                            "Write the evidence memo now."
                        ),
                    },
                ]
            )
        return {
            "answer": answer,
            "retrieval_query": retrieval_query,
            "evidence": evidence,
            "sources": [hit.to_dict() for hit in hits],
        }
