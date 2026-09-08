from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import RAGConfig
from .pdf_ingest import batched, discover_pdfs, parse_pdf, sha256_file
from .siliconflow import SiliconFlowClient

TABLE_NAME = "paper_chunks"
PARSER_VERSION = 3


def _lancedb():
    try:
        import lancedb
    except ImportError as exc:
        raise RuntimeError("缺少 lancedb，请执行: python -m pip install -r requirements-rag.txt") from exc
    return lancedb


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "documents": {}, "duplicates": {}, "errors": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class PaperIndexer:
    def __init__(self, config: RAGConfig, client: SiliconFlowClient | None = None):
        self.config = config
        self.client = client or SiliconFlowClient(config)

    def _open(self):
        self.config.index_dir.mkdir(parents=True, exist_ok=True)
        return _lancedb().connect(str(self.config.db_dir))

    def run(self, rebuild: bool = False, limit: int | None = None) -> dict[str, Any]:
        if not self.config.data_dir.exists():
            raise FileNotFoundError(f"RAG data directory not found: {self.config.data_dir}")
        db = self._open()
        table_names = set(db.table_names())
        if rebuild and TABLE_NAME in table_names:
            db.drop_table(TABLE_NAME)
            table_names.remove(TABLE_NAME)
        manifest = (
            {"version": 1, "documents": {}, "duplicates": {}, "errors": {}}
            if rebuild
            else load_manifest(self.config.manifest_path)
        )
        prior_model = manifest.get("embedding_model")
        if prior_model and prior_model != self.config.embedding_model and TABLE_NAME in table_names:
            raise RuntimeError(
                f"索引由 {prior_model} 生成，当前配置为 {self.config.embedding_model}；请使用 --rebuild 重建。"
            )
        signature = {
            "parser_version": PARSER_VERSION,
            "embedding_model": self.config.embedding_model,
            "chunk_chars": self.config.chunk_chars,
            "chunk_overlap_chars": self.config.chunk_overlap_chars,
        }
        prior_signature = manifest.get("index_signature")
        if prior_signature and prior_signature != signature and TABLE_NAME in table_names:
            raise RuntimeError("解析器、分块或 embedding 配置已变化；请使用 --rebuild 重建索引。")
        manifest["embedding_model"] = self.config.embedding_model
        manifest["index_signature"] = signature
        manifest["data_dir"] = str(self.config.data_dir.resolve())

        all_paths = discover_pdfs(self.config.data_dir)
        paths = all_paths
        if limit is not None:
            paths = paths[:limit]
        known_hashes = {
            item["sha256"]: relative_path
            for relative_path, item in manifest.get("documents", {}).items()
            if item.get("sha256")
        }
        table = db.open_table(TABLE_NAME) if TABLE_NAME in table_names else None
        summary = {
            "discovered": len(all_paths),
            "selected": len(paths),
            "limit": limit,
            "indexed": 0,
            "skipped": 0,
            "duplicates": 0,
            "failed": 0,
            "chunks": 0,
        }

        for position, path in enumerate(paths, start=1):
            relative_path = str(path.relative_to(self.config.data_dir))
            try:
                digest = sha256_file(path)
                existing = manifest["documents"].get(relative_path)
                if existing and existing.get("sha256") == digest:
                    summary["skipped"] += 1
                    print(f"[{position}/{len(paths)}] skip unchanged: {relative_path}")
                    continue
                duplicate_of = known_hashes.get(digest)
                if duplicate_of and duplicate_of != relative_path:
                    manifest["duplicates"][relative_path] = duplicate_of
                    summary["duplicates"] += 1
                    print(f"[{position}/{len(paths)}] skip duplicate: {relative_path}")
                    save_manifest(self.config.manifest_path, manifest)
                    continue

                parsed = parse_pdf(
                    path=path,
                    data_dir=self.config.data_dir,
                    chunk_chars=self.config.chunk_chars,
                    overlap_chars=self.config.chunk_overlap_chars,
                    known_sha256=digest,
                )
                if not parsed.chunks:
                    raise RuntimeError("PDF has no extractable text (OCR required)")

                if existing and table is not None:
                    old_doc_id = str(existing.get("sha256", ""))
                    if old_doc_id:
                        table.delete(f"doc_id = '{old_doc_id}'")

                records: list[dict[str, Any]] = []
                for batch in batched(parsed.chunks, self.config.embedding_batch_size):
                    vectors = self.client.embed([chunk.search_text for chunk in batch])
                    for chunk, vector in zip(batch, vectors):
                        chunk.vector = vector
                        records.append(chunk.to_record())
                if table is None:
                    table = db.create_table(TABLE_NAME, data=records, mode="create")
                else:
                    table.add(records)

                manifest["documents"][relative_path] = {
                    "sha256": digest,
                    "title": parsed.title,
                    "collection": parsed.collection,
                    "pages": parsed.page_count,
                    "chunks": len(records),
                    "warnings": parsed.warnings,
                    "indexed_at": int(time.time()),
                }
                manifest["errors"].pop(relative_path, None)
                known_hashes[digest] = relative_path
                summary["indexed"] += 1
                summary["chunks"] += len(records)
                save_manifest(self.config.manifest_path, manifest)
                print(f"[{position}/{len(paths)}] indexed {len(records)} chunks: {relative_path}")
            except Exception as exc:  # noqa: BLE001
                summary["failed"] += 1
                manifest["errors"][relative_path] = f"{type(exc).__name__}: {exc}"
                save_manifest(self.config.manifest_path, manifest)
                print(f"[{position}/{len(paths)}] FAILED {relative_path}: {exc}")

        if table is not None:
            table.create_fts_index("search_text", replace=True)
            summary["total_rows"] = table.count_rows()
        else:
            summary["total_rows"] = 0
        summary["complete"] = limit is None and summary["failed"] == 0
        manifest["last_run"] = summary
        save_manifest(self.config.manifest_path, manifest)
        return summary


def index_stats(config: RAGConfig) -> dict[str, Any]:
    manifest = load_manifest(config.manifest_path)
    stats: dict[str, Any] = {
        "index_exists": config.manifest_path.exists(),
        "embedding_model": manifest.get("embedding_model"),
        "documents": len(manifest.get("documents", {})),
        "duplicates": len(manifest.get("duplicates", {})),
        "errors": len(manifest.get("errors", {})),
        "chunks": sum(int(item.get("chunks", 0)) for item in manifest.get("documents", {}).values()),
        "complete": bool(manifest.get("last_run", {}).get("complete", False)),
    }
    try:
        db = _lancedb().connect(str(config.db_dir))
        stats["rows"] = db.open_table(TABLE_NAME).count_rows() if TABLE_NAME in db.table_names() else 0
    except Exception:  # noqa: BLE001
        stats["rows"] = 0
    return stats
