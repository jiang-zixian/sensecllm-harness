from __future__ import annotations

from collections import defaultdict
from typing import Any

from .config import RAGConfig
from .indexer import TABLE_NAME, _lancedb
from .models import SearchHit
from .query import build_fts_query


class HybridStore:
    def __init__(self, config: RAGConfig):
        self.config = config
        db = _lancedb().connect(str(config.db_dir))
        if TABLE_NAME not in db.table_names():
            raise RuntimeError("RAG 索引不存在，请先运行 `python -m sensor_rag index`。")
        self.table = db.open_table(TABLE_NAME)

    def _vector_search(self, vector: list[float]) -> list[dict[str, Any]]:
        return (
            self.table.search(vector, query_type="vector")
            .distance_type("cosine")
            .limit(self.config.retrieval_pool)
            .to_list()
        )

    def _fts_search(self, query: str) -> list[dict[str, Any]]:
        fts_query = build_fts_query(query)
        for candidate in (fts_query, query):
            try:
                return (
                    self.table.search(candidate, query_type="fts", fts_columns="search_text")
                    .limit(self.config.retrieval_pool)
                    .to_list()
                )
            except Exception:
                continue
        return []

    def hybrid_candidates(self, query: str, vector: list[float]) -> list[SearchHit]:
        vector_rows = self._vector_search(vector)
        fts_rows = self._fts_search(query)
        fused: dict[str, float] = defaultdict(float)
        records: dict[str, dict[str, Any]] = {}
        rrf_k = 60.0
        for rows, weight in ((vector_rows, 1.0), (fts_rows, 0.85)):
            for rank, record in enumerate(rows, start=1):
                chunk_id = str(record["chunk_id"])
                records[chunk_id] = record
                fused[chunk_id] += weight / (rrf_k + rank)
        for chunk_id, record in records.items():
            if record.get("collection") == "strong_related_papers":
                fused[chunk_id] *= 1.06

        ranked_ids = sorted(fused, key=fused.get, reverse=True)
        per_doc: dict[str, int] = defaultdict(int)
        candidates: list[SearchHit] = []
        for chunk_id in ranked_ids:
            record = records[chunk_id]
            doc_id = str(record["doc_id"])
            if per_doc[doc_id] >= self.config.max_chunks_per_paper:
                continue
            hit = SearchHit.from_record(record)
            hit.fused_score = fused[chunk_id]
            candidates.append(hit)
            per_doc[doc_id] += 1
            if len(candidates) >= self.config.rerank_pool:
                break
        return candidates
