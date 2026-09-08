from __future__ import annotations

from pathlib import Path

from sensor_rag.config import RAGConfig
from sensor_rag.pipeline import SensorRAG
from sensor_rag.web import WebHit


class FakeClient:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def rerank(self, _query: str, docs: list[str], top_n: int) -> list[dict[str, float]]:
        return [{"index": index, "relevance_score": 0.9} for index, _ in enumerate(docs[:top_n])]

    def chat(self, _messages):
        return "grounded answer"


class FakeStore:
    def hybrid_candidates(self, _query: str, _vector: list[float]):
        return []


class FakeWeb:
    def search(self, _query: str):
        return [
            WebHit(
                title="Recent MEMS microphone attack note",
                url="https://example.test/mems",
                snippet="A recent public note discusses ultrasonic MEMS microphone injection.",
                provider="test",
                rank=1,
            )
        ]


def test_sensor_rag_merges_web_knowledge_into_evidence_pack(tmp_path: Path) -> None:
    config = RAGConfig(
        data_dir=tmp_path,
        index_dir=tmp_path / "index",
        api_key="test",
        web_rag_enabled=True,
    )
    rag = SensorRAG(config=config, client=FakeClient(), store=FakeStore(), web_retriever=FakeWeb())

    result = rag.answer("MEMS microphone ultrasonic injection", evidence_only=True)

    assert "Paper evidence:" in result["evidence"]
    assert "Web knowledge:" in result["evidence"]
    assert result["web_sources"][0]["source_type"] == "web"
    assert result["web_sources"][0]["url"] == "https://example.test/mems"
