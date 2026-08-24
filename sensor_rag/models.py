from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PaperChunk:
    chunk_id: str
    doc_id: str
    source_path: str
    title: str
    collection: str
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    search_text: str
    vector: list[float] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "title": self.title,
            "collection": self.collection,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "search_text": self.search_text,
            "vector": self.vector,
        }


@dataclass
class ParsedPaper:
    path: Path
    relative_path: str
    doc_id: str
    title: str
    collection: str
    page_count: int
    chunks: list[PaperChunk]
    warnings: list[str] = field(default_factory=list)


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    source_path: str
    title: str
    collection: str
    page_start: int
    page_end: int
    chunk_index: int
    text: str
    fused_score: float = 0.0
    rerank_score: float = 0.0

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "SearchHit":
        return cls(
            chunk_id=str(record["chunk_id"]),
            doc_id=str(record["doc_id"]),
            source_path=str(record["source_path"]),
            title=str(record["title"]),
            collection=str(record.get("collection", "")),
            page_start=int(record["page_start"]),
            page_end=int(record["page_end"]),
            chunk_index=int(record["chunk_index"]),
            text=str(record["text"]),
        )

    def citation(self, number: int) -> str:
        pages = str(self.page_start) if self.page_start == self.page_end else f"{self.page_start}-{self.page_end}"
        return f"[S{number}] {self.title}, pp. {pages}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "title": self.title,
            "collection": self.collection,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "fused_score": round(self.fused_score, 6),
            "rerank_score": round(self.rerank_score, 6),
            "text": self.text,
        }

