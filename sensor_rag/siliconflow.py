from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Iterable

from .config import RAGConfig


class SiliconFlowError(RuntimeError):
    pass


class SiliconFlowClient:
    """Small dependency-free client for SiliconFlow's OpenAI-compatible APIs."""

    def __init__(self, config: RAGConfig):
        config.require_api_key()
        self.config = config

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.api_base.rstrip('/')}/{endpoint.lstrip('/')}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = SiliconFlowError(f"SiliconFlow HTTP {exc.code}: {detail}")
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt + 1 < self.config.max_retries:
                time.sleep(min(8.0, 0.8 * (2**attempt)) + random.random() * 0.25)
        raise SiliconFlowError(f"SiliconFlow request failed after retries: {last_error}")

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        items = [text.strip() for text in texts]
        if not items or any(not text for text in items):
            raise ValueError("Embedding input must contain non-empty strings")
        data = self._post(
            "embeddings",
            {"model": self.config.embedding_model, "input": items, "encoding_format": "float"},
        ).get("data", [])
        ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors = [item.get("embedding") for item in ordered]
        if len(vectors) != len(items) or any(not vector for vector in vectors):
            raise SiliconFlowError("Embedding response is incomplete")
        return vectors

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        if not documents:
            return []
        response = self._post(
            "rerank",
            {
                "model": self.config.reranker_model,
                "query": query,
                "documents": documents,
                "top_n": min(top_n, len(documents)),
                "return_documents": False,
                "max_chunks_per_doc": 8,
                "overlap_tokens": 64,
            },
        )
        return list(response.get("results", []))

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 2200) -> str:
        response = self._post(
            "chat/completions",
            {
                "model": self.config.generation_model,
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "top_p": 0.8,
            },
        )
        try:
            return str(response["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise SiliconFlowError("Chat response does not contain assistant content") from exc

