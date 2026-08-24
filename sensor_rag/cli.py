from __future__ import annotations

import argparse
import json

from .config import RAGConfig
from .indexer import PaperIndexer, index_stats
from .pipeline import SensorRAG
from .service import serve
from .siliconflow import SiliconFlowClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SenSec paper RAG")
    commands = parser.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index", help="parse PDFs and build/update the index")
    index.add_argument("--rebuild", action="store_true", help="drop and rebuild the whole index")
    index.add_argument("--limit", type=int, help="index only the first N PDFs (smoke testing)")

    commands.add_parser("stats", help="show local index statistics")
    commands.add_parser("serve", help="start the Dify-compatible HTTP service")

    query = commands.add_parser("query", help="run one retrieval/query from the terminal")
    query.add_argument("query")
    query.add_argument("--rag-input")
    query.add_argument("--evidence-only", action="store_true")

    commands.add_parser("check-api", help="test embedding and reranking APIs without indexing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RAGConfig()
    if args.command == "index":
        summary = PaperIndexer(config).run(rebuild=args.rebuild, limit=args.limit)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.command == "stats":
        print(json.dumps(index_stats(config), ensure_ascii=False, indent=2))
    elif args.command == "serve":
        config.require_api_key()
        serve(config)
    elif args.command == "query":
        result = SensorRAG(config).answer(args.query, args.rag_input, evidence_only=args.evidence_only)
        print(result["answer"])
        print("\n--- sources ---")
        print(json.dumps(result["sources"], ensure_ascii=False, indent=2))
    elif args.command == "check-api":
        client = SiliconFlowClient(config)
        vectors = client.embed(["MEMS accelerometer acoustic signal injection"])
        ranked = client.rerank("accelerometer acoustic attack", ["acoustic resonance attack", "weather report"], 2)
        print(json.dumps({"embedding_dimensions": len(vectors[0]), "rerank": ranked}, ensure_ascii=False, indent=2))
    return 0

