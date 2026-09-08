"""Local, API-free chunking sweep for the interview notes.

This intentionally exercises the production PDF parser without changing the
index or calling an embedding provider.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from sensor_rag.config import PROJECT_ROOT
from sensor_rag.pdf_ingest import discover_pdfs, parse_pdf


CONFIGS = (
    (1000, 100),
    (1500, 200),
    (2400, 320),
    (3000, 450),
)


def main() -> None:
    data_dir = PROJECT_ROOT / "RAG_data"
    rows: list[dict[str, object]] = []
    # Keep the sweep fast and reproducible: the sample includes the primary
    # paper plus four related papers with different PDF layouts.
    paths = discover_pdfs(data_dir)[:5]
    for chunk_chars, overlap in CONFIGS:
        counts: list[int] = []
        lengths: list[int] = []
        short_chunks = 0
        empty_docs = 0
        for path in paths:
            parsed = parse_pdf(path, data_dir, chunk_chars, overlap)
            counts.append(len(parsed.chunks))
            lengths.extend(len(chunk.text) for chunk in parsed.chunks)
            short_chunks += sum(len(chunk.text) < 160 for chunk in parsed.chunks)
            empty_docs += not bool(parsed.chunks)
        rows.append(
            {
                "chunk_chars": chunk_chars,
                "overlap_chars": overlap,
                "documents": len(paths),
                "sample_paths": [str(path.relative_to(data_dir)) for path in paths],
                "chunks": sum(counts),
                "median_chunks_per_document": statistics.median(counts) if counts else 0,
                "median_chunk_chars": statistics.median(lengths) if lengths else 0,
                "p95_chunk_chars": (
                    sorted(lengths)[min(len(lengths) - 1, int(len(lengths) * 0.95))]
                    if lengths
                    else 0
                ),
                "short_chunks_lt_160": short_chunks,
                "empty_documents": empty_docs,
            }
        )
    output = PROJECT_ROOT / "experiments" / "rag_interview" / "chunk_sweep.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"configs": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
