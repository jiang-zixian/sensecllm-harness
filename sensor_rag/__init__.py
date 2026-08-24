"""A compact, paper-focused RAG service for SenSecLLM."""

from .config import RAGConfig
from .pipeline import SensorRAG

__all__ = ["RAGConfig", "SensorRAG"]

