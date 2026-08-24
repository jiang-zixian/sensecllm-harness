from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def benchmark_sensor_models(
    sensor_dir: Path = PROJECT_ROOT / "sensor_input" / "all",
) -> list[str]:
    """Return benchmark model identifiers that must never enter RAG evidence."""
    if not sensor_dir.exists():
        return []
    models: list[str] = []
    for path in sorted(item for item in sensor_dir.iterdir() if item.is_file()):
        match = re.match(r"^(.+?)-(?=[\u4e00-\u9fff])", path.stem)
        model = (match.group(1) if match else path.stem).strip()
        if model:
            models.append(model)
    return list(dict.fromkeys(models))


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


@dataclass(frozen=True)
class RAGConfig:
    data_dir: Path = Path(os.getenv("RAG_DATA_DIR", str(PROJECT_ROOT / "RAG_data")))
    index_dir: Path = Path(os.getenv("RAG_INDEX_DIR", str(PROJECT_ROOT / ".rag_index")))
    api_base: str = os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1")
    api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    reranker_model: str = os.getenv("RAG_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    generation_model: str = os.getenv("RAG_GENERATION_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507")
    chunk_chars: int = _env_int("RAG_CHUNK_CHARS", 2400)
    chunk_overlap_chars: int = _env_int("RAG_CHUNK_OVERLAP_CHARS", 320)
    embedding_batch_size: int = _env_int("RAG_EMBEDDING_BATCH_SIZE", 16)
    retrieval_pool: int = _env_int("RAG_RETRIEVAL_POOL", 50)
    rerank_pool: int = _env_int("RAG_RERANK_POOL", 24)
    top_k: int = _env_int("RAG_TOP_K", 7)
    rerank_threshold: float = _env_float("RAG_RERANK_THRESHOLD", 0.18)
    max_chunks_per_paper: int = _env_int("RAG_MAX_CHUNKS_PER_PAPER", 2)
    request_timeout: int = _env_int("RAG_REQUEST_TIMEOUT", 120)
    max_retries: int = _env_int("RAG_MAX_RETRIES", 4)
    host: str = os.getenv("RAG_HOST", "127.0.0.1")
    port: int = _env_int("RAG_PORT", 8001)

    @property
    def db_dir(self) -> Path:
        return self.index_dir / "lancedb"

    @property
    def manifest_path(self) -> Path:
        return self.index_dir / "manifest.json"

    def require_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "缺少 SILICONFLOW_API_KEY。请先设置环境变量，API key 不应写入代码。"
            )
