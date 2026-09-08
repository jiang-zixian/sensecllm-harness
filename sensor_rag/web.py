from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from .config import RAGConfig


@dataclass(frozen=True)
class WebHit:
    title: str
    url: str
    snippet: str
    provider: str
    rank: int

    def citation(self, number: int) -> str:
        return f"[W{number}] {self.title} ({self.url})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": "web",
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "provider": self.provider,
            "rank": self.rank,
        }


class WebKnowledgeRetriever:
    """Fetch compact web snippets for RAG grounding when a search API key exists."""

    def __init__(self, config: RAGConfig) -> None:
        self.config = config

    @property
    def available_provider(self) -> str | None:
        if os.getenv("TAVILY_API_KEY"):
            return "tavily"
        if os.getenv("BRAVE_SEARCH_API_KEY"):
            return "brave"
        if os.getenv("SERPAPI_API_KEY"):
            return "serpapi"
        return None

    def search(self, query: str) -> list[WebHit]:
        provider = self.available_provider
        if not provider or not self.config.web_rag_enabled:
            return []
        try:
            if provider == "tavily":
                return self._search_tavily(query)
            if provider == "brave":
                return self._search_brave(query)
            return self._search_serpapi(query)
        except requests.RequestException:
            return []

    def _search_tavily(self, query: str) -> list[WebHit]:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": os.environ["TAVILY_API_KEY"],
                "query": query,
                "search_depth": "basic",
                "max_results": self.config.web_top_k,
                "include_answer": False,
            },
            timeout=self.config.web_request_timeout,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        return [
            WebHit(
                title=str(item.get("title") or item.get("url") or "Untitled web result"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                provider="tavily",
                rank=index,
            )
            for index, item in enumerate(results[: self.config.web_top_k], start=1)
            if item.get("url")
        ]

    def _search_brave(self, query: str) -> list[WebHit]:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": self.config.web_top_k},
            headers={"X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"]},
            timeout=self.config.web_request_timeout,
        )
        response.raise_for_status()
        results = (response.json().get("web") or {}).get("results") or []
        return [
            WebHit(
                title=str(item.get("title") or item.get("url") or "Untitled web result"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("description") or ""),
                provider="brave",
                rank=index,
            )
            for index, item in enumerate(results[: self.config.web_top_k], start=1)
            if item.get("url")
        ]

    def _search_serpapi(self, query: str) -> list[WebHit]:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": os.environ["SERPAPI_API_KEY"],
                "num": self.config.web_top_k,
            },
            timeout=self.config.web_request_timeout,
        )
        response.raise_for_status()
        results = response.json().get("organic_results") or []
        return [
            WebHit(
                title=str(item.get("title") or item.get("link") or "Untitled web result"),
                url=str(item.get("link") or ""),
                snippet=str(item.get("snippet") or ""),
                provider="serpapi",
                rank=index,
            )
            for index, item in enumerate(results[: self.config.web_top_k], start=1)
            if item.get("link")
        ]


def web_evidence_pack(hits: list[WebHit]) -> str:
    if not hits:
        return (
            "No web knowledge was retrieved. Configure TAVILY_API_KEY, "
            "BRAVE_SEARCH_API_KEY, or SERPAPI_API_KEY to enable web RAG."
        )
    blocks = []
    for number, hit in enumerate(hits, start=1):
        blocks.append(
            f"{hit.citation(number)}\n"
            f"Provider: {hit.provider}\n"
            f"Rank: {hit.rank}\n"
            f"Snippet:\n{hit.snippet}"
        )
    return "\n\n---\n\n".join(blocks)
