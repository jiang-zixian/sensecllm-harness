from __future__ import annotations

from dataclasses import dataclass

from sensecllm.models.chatanywhere import ChatAnywhereGateway


@dataclass
class FakeResponse:
    status_code: int = 200

    def json(self):
        return {"choices": [{"message": {"content": '```json\n{"decision":"approve"}\n```'}}]}


def test_chatanywhere_gateway_uses_requested_deepseek_model(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)
    gateway = ChatAnywhereGateway(api_key="test-key", base_url="https://gateway.example/v1")
    result = gateway.complete_json(
        model="deepseek-v3.2",
        system_prompt="critic",
        user_prompt="payload",
    )

    assert result == {"decision": "approve"}
    assert captured["url"] == "https://gateway.example/v1/chat/completions"
    assert captured["json"]["model"] == "deepseek-v3.2"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
