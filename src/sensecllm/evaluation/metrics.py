from __future__ import annotations

import math
import re
from typing import Any


def normalize_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def set_prf(predicted: list[Any], expected: list[Any]) -> dict[str, float | int]:
    predicted_set = {normalize_label(item) for item in predicted if normalize_label(item)}
    expected_set = {normalize_label(item) for item in expected if normalize_label(item)}
    true_positive = len(predicted_set & expected_set)
    precision = true_positive / len(predicted_set) if predicted_set else float(not expected_set)
    recall = true_positive / len(expected_set) if expected_set else float(not predicted_set)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "predicted_count": len(predicted_set),
        "expected_count": len(expected_set),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def retrieval_recall_at_k(ranked_ids: list[str], relevant_ids: list[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 1.0
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked_ids: list[str], relevant_ids: list[str]) -> float:
    relevant = set(relevant_ids)
    for rank, item in enumerate(ranked_ids, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevance: dict[str, float], k: int) -> float:
    def dcg(scores: list[float]) -> float:
        return sum((2**score - 1) / math.log2(index + 2) for index, score in enumerate(scores))

    actual = [float(relevance.get(item, 0.0)) for item in ranked_ids[:k]]
    ideal = sorted((float(value) for value in relevance.values()), reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    return dcg(actual) / ideal_dcg if ideal_dcg else 1.0
