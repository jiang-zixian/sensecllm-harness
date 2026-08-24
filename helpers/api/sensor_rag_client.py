"""Drop-in helper for RAG-only calls; general Dify applications remain untouched."""

from __future__ import annotations

import os

from helpers.api.dify_client import ask_dify


def ask_sensor_rag(
    question: str,
    api_key: str = "sensor-rag-local",
    RAGinput: str | None = None,
    conv_id: str | None = None,
    user: str = "healer_jzx",
    api_url: str | None = None,
    max_retry: int = 3,
    silent: bool = False,
    exclude_terms: list[str] | None = None,
):
    """Call the local service with the same return shape as ``ask_dify``."""
    if os.getenv("SENSECLLM_RAG_ENABLED", "true").casefold() in {"0", "false", "no", "off"}:
        return "RAG disabled by an explicit experiment configuration; no literature evidence supplied.", conv_id
    return ask_dify(
        question=question,
        api_key=api_key,
        RAGinput=RAGinput,
        conv_id=conv_id,
        user=user,
        api_url=api_url or os.getenv("SENSOR_RAG_URL", "http://127.0.0.1:8001/v1/chat-messages"),
        max_retry=max_retry,
        silent=silent,
        inputs_extra={"mode": "evidence", "exclude_terms": exclude_terms or []},
    )
