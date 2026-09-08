"""Compare retrieval quality for the two isolated five-document chunk indexes."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from systematic_benchmark import CASES, evaluate
from sensor_rag.config import PROJECT_ROOT, RAGConfig


PREFIXES = {
    "4caad3be4125706f3d1f",
    "d358b1bd1cd80526bdba",
    "7d73832060ecaa71aa52",
    "d5f526bf05fe1820c7a9",
    "21cdc1629a1745c5989e",
}


def config_for(index_name: str, chunk: int, overlap: int) -> RAGConfig:
    os.environ["RAG_INDEX_DIR"] = str(PROJECT_ROOT / "experiments" / "rag_interview" / index_name)
    os.environ["RAG_CHUNK_CHARS"] = str(chunk)
    os.environ["RAG_CHUNK_OVERLAP_CHARS"] = str(overlap)
    return replace(RAGConfig(), chunk_chars=chunk, chunk_overlap_chars=overlap)


def main() -> None:
    cases = [case for case in CASES if case[2] in PREFIXES]
    results = {
        "benchmark_type": "paired five-document chunk-configuration benchmark",
        "case_count": len(cases),
        "1000_100": evaluate(config_for("index_1000", 1000, 100), cases),
        "2400_320": evaluate(config_for("index_2400", 2400, 320), cases),
    }
    path = PROJECT_ROOT / "experiments" / "rag_interview" / "systematic" / "chunk_retrieval.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value["metrics"] for key, value in results.items() if isinstance(value, dict) and "metrics" in value}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
