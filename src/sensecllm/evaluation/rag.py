from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Protocol

from .metrics import ndcg_at_k, reciprocal_rank, retrieval_recall_at_k


class Retriever(Protocol):
    def retrieve(self, query: str, rag_input: str | None = None) -> tuple[str, list[Any]]: ...


def evaluate_rag(retriever: Retriever, judgments_path: Path, k: int = 5) -> dict[str, Any]:
    judgments = json.loads(judgments_path.read_text(encoding="utf-8"))
    cases = judgments.get("cases", judgments) if isinstance(judgments, dict) else judgments
    results = []
    for case in cases:
        _query, hits = retriever.retrieve(str(case["query"]), case.get("rag_input"))
        ranked_ids = [str(getattr(hit, "chunk_id", getattr(hit, "doc_id", ""))) for hit in hits]
        relevant = [str(item) for item in case.get("relevant_ids", [])]
        relevance = {str(key): float(value) for key, value in case.get("relevance", {}).items()}
        results.append(
            {
                "case_id": case.get("case_id", ""),
                "ranked_ids": ranked_ids,
                "recall_at_k": retrieval_recall_at_k(ranked_ids, relevant, k),
                "mrr": reciprocal_rank(ranked_ids, relevant),
                "ndcg_at_k": ndcg_at_k(ranked_ids, relevance, k),
            }
        )
    metrics = {
        key: round(statistics.fmean(item[key] for item in results), 6) if results else 0.0
        for key in ("recall_at_k", "mrr", "ndcg_at_k")
    }
    return {"schema_version": "1.0", "k": k, "case_count": len(results), "metrics": metrics, "cases": results}
