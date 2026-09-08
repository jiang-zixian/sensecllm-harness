"""Systematic, reproducible retrieval ablation for the interview notes."""

from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from sensor_rag.config import PROJECT_ROOT, RAGConfig
from sensor_rag.models import SearchHit
from sensor_rag.pipeline import SensorRAG
from sensor_rag.query import build_retrieval_query
from sensor_rag.siliconflow import SiliconFlowClient
from sensor_rag.store import HybridStore


# Labels are document-level and derived from the indexed paper titles. These
# cases validate retrieval engineering, not passage-level scientific relevance.
CASES = [
    ("phyfuzz", "How can physical sensor attack surfaces be fuzzed automatically?", "4caad3be4125706f3d1f"),
    ("pad", "How does adversarial training protect power systems from denial-of-service attacks?", "d358b1bd1cd80526bdba"),
    ("v2g-auth", "Cross-domain certificateless consortium blockchain authentication for vehicle-to-grid networks", "7d73832060ecaa71aa52"),
    ("assistant-vetting", "Security review process for third-party smart-home assistant applications", "d5f526bf05fe1820c7a9"),
    ("ultrasound-defense", "Fourier-transform defense against inaudible ultrasonic command attacks", "21cdc1629a1745c5989e"),
    ("audio-multiversion", "Detect audio adversarial examples with multiversion programming", "e9dfc038a193d471f446"),
    ("pv-emi", "Electromagnetic interference attack exploiting photovoltaic inverter control", "355c90ec5bf76f086d87"),
    ("bitcoin-2fa", "Privacy-preserving two-factor authentication for Bitcoin SPV clients", "38ffcefd129191385ca5"),
    ("rfid-gspn", "GSPN reliability performance model for RFID anti-collision under noisy channels", "8ef4aa3deb78fd37f1be"),
    ("smart-building-review", "Review of cyber physical security threats in smart buildings and infrastructure", "025cb9e0748a5ee1d49d"),
    ("smart-grid-routing", "Reliable backup routing for neighborhood area networks in smart grids", "c81675e3ab215132f29f"),
    ("amazon-echo", "What security and privacy risks are associated with Amazon Echo?", "f9130c42a599aaa12e5b"),
    ("industrial-wireless", "Survey of anomaly detection for industrial wireless sensor networks in water infrastructure", "aeea0d9182ecbbab6fb8"),
    ("aml-taxonomy", "System-driven taxonomy of adversarial machine learning attacks and defenses", "9c468ec62115735b0f4d"),
    ("automotive-taxonomy", "Taxonomy of attack mechanisms in connected automotive systems", "8d5cf0dcc07975de33eb"),
    ("signal-framework", "Framework for evaluating security under physical signal injection attacks", "5cc65b24ff18ac414c0b"),
    ("adversarial-survey", "Survey of adversarial attacks and defense techniques", "5676574cab51403268d6"),
    ("rf-fingerprint", "Identify a fingertip or device using profiled radio-frequency fingerprints", "264964eedfe434e2b489"),
    ("fmcw-radar", "Frequency-domain spoofing of FMCW radar mitigated by a hybrid chirp waveform", "f29a3429a3263c56ab32"),
    ("microgrid-flow", "Detect microgrid controller attacks by monitoring message flow", "e7e29c864bc287d12181"),
    # Short/identifier-heavy variants exercise the keyword branch.
    ("phyfuzz-short", "PhyFuzz sensor fuzzing", "4caad3be4125706f3d1f"),
    ("pad-short", "@PAD power DoS", "d358b1bd1cd80526bdba"),
    ("v2g-short", "3C V2G authentication", "7d73832060ecaa71aa52"),
    ("echo-short", "Amazon Echo privacy", "f9130c42a599aaa12e5b"),
    ("fmcw-short", "FMCW hybrid chirp spoofing", "f29a3429a3263c56ab32"),
    ("spv-short", "Bitcoin SPV 2FA", "38ffcefd129191385ca5"),
    ("emi-short", "PV inverter EMI attack", "355c90ec5bf76f086d87"),
    ("rfid-short", "RFID GSPN anti-collision", "8ef4aa3deb78fd37f1be"),
    ("ultrasound-short", "inaudible ultrasound Fourier defense", "21cdc1629a1745c5989e"),
    ("microgrid-short", "microgrid message-flow security monitor", "e7e29c864bc287d12181"),
]


def doc_ids(rows: list[dict[str, Any]] | list[SearchHit]) -> list[str]:
    values = []
    for row in rows:
        value = row.doc_id if isinstance(row, SearchHit) else str(row["doc_id"])
        if value not in values:
            values.append(value)
    return values


def metric(rows: list[dict[str, Any]], method: str) -> dict[str, float]:
    ranks = [row["ranks"].get(method) for row in rows]
    top1 = sum(rank == 1 for rank in ranks) / len(ranks)
    hit5 = sum(rank is not None and rank <= 5 for rank in ranks) / len(ranks)
    mrr = sum(1 / rank for rank in ranks if rank is not None) / len(ranks)
    return {"top1_accuracy": top1, "hit_at_5": hit5, "mrr": mrr}


def rank_of(ids: list[str], relevant_prefix: str) -> int | None:
    for rank, value in enumerate(ids, 1):
        if value.startswith(relevant_prefix):
            return rank
    return None


def evaluate(config: RAGConfig, cases=CASES) -> dict[str, Any]:
    client = SiliconFlowClient(config)
    store = HybridStore(config)
    queries = [build_retrieval_query(query, None) for _, query, _ in cases]
    started = time.perf_counter()
    vectors = client.embed(queries)
    embedding_seconds = time.perf_counter() - started
    rows = []
    method_times: dict[str, list[float]] = {name: [] for name in ("vector", "fts", "hybrid", "rerank", "production_final")}
    for (case_id, raw_query, relevant), query, vector in zip(cases, queries, vectors):
        started = time.perf_counter()
        vector_ids = doc_ids(store._vector_search(vector))
        method_times["vector"].append(time.perf_counter() - started)
        started = time.perf_counter()
        fts_ids = doc_ids(store._fts_search(query))
        method_times["fts"].append(time.perf_counter() - started)
        started = time.perf_counter()
        candidates = store.hybrid_candidates(query, vector)
        hybrid_ids = doc_ids(candidates)
        method_times["hybrid"].append(time.perf_counter() - started)
        started = time.perf_counter()
        docs = [f"Paper: {hit.title}\nPages: {hit.page_start}-{hit.page_end}\n{hit.text}" for hit in candidates]
        reranked = client.rerank(query, docs, top_n=len(docs))
        ranked_hits = [candidates[int(item["index"])] for item in reranked]
        rerank_ids = doc_ids(ranked_hits)
        rerank_elapsed = time.perf_counter() - started
        method_times["rerank"].append(rerank_elapsed)
        selected: list[SearchHit] = []
        per_doc: dict[str, int] = {}
        for item in reranked:
            hit = candidates[int(item["index"])]
            if float(item.get("relevance_score", 0.0)) < config.rerank_threshold:
                continue
            if per_doc.get(hit.doc_id, 0) >= config.max_chunks_per_paper:
                continue
            selected.append(hit)
            per_doc[hit.doc_id] = per_doc.get(hit.doc_id, 0) + 1
            if len(selected) >= config.top_k:
                break
        production_ids = doc_ids(selected)
        method_times["production_final"].append(rerank_elapsed)
        rows.append(
            {
                "case_id": case_id,
                "query": raw_query,
                "relevant_doc_prefix": relevant,
                "ranks": {
                    "vector": rank_of(vector_ids, relevant),
                    "fts": rank_of(fts_ids, relevant),
                    "hybrid": rank_of(hybrid_ids, relevant),
                    "rerank": rank_of(rerank_ids, relevant),
                    "production_final": rank_of(production_ids, relevant),
                },
                "top5": {
                    "vector": vector_ids[:5],
                    "fts": fts_ids[:5],
                    "hybrid": hybrid_ids[:5],
                    "rerank": rerank_ids[:5],
                    "production_final": production_ids[:5],
                },
            }
        )
    methods = {name: metric(rows, name) for name in method_times}
    latency = {
        name: {
            "median_ms": statistics.median(values) * 1000,
            "p95_ms": sorted(values)[min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)] * 1000,
        }
        for name, values in method_times.items()
    }
    return {
        "benchmark_type": "document-title/topic engineering benchmark",
        "case_count": len(cases),
        "embedding_batch_seconds": embedding_seconds,
        "metrics": methods,
        "latency": latency,
        "cases": rows,
    }


def main() -> None:
    output_dir = PROJECT_ROOT / "experiments" / "rag_interview" / "systematic"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = evaluate(RAGConfig())
    path = output_dir / "retrieval_ablation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "metrics": result["metrics"], "latency": result["latency"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
