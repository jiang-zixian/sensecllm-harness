from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from sensecllm.observability.usage import record_model_usage


class ChatAnywhereGateway:
    """Minimal OpenAI-compatible gateway for ChatAnywhere DeepSeek models."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 180,
        usage_file: str | os.PathLike[str] | None = None,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("CHATANYWHERE_API_KEY", "")
        ).strip()
        resolved_base_url = base_url or os.getenv("CHATANYWHERE_BASE_URL")
        self.base_url = (resolved_base_url or "https://api.chatanywhere.tech/v1").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.usage_file = usage_file

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("CHATANYWHERE_API_KEY is not configured")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise RuntimeError(f"ChatAnywhere request failed with HTTP {response.status_code}")
        payload = response.json()
        record_model_usage(
            os.fspath(self.usage_file) if self.usage_file is not None else None,
            provider="chatanywhere",
            model=model,
            usage=payload.get("usage"),
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("ChatAnywhere returned an unexpected response schema") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("ChatAnywhere returned empty content")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise TypeError("ChatAnywhere JSON response must be an object")
        return result
