from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from sensecllm.api import app as api_module
from sensecllm.config import HarnessSettings
from sensecllm.harness.runner import HarnessRunner

from .test_harness_runner import FakeLegacyAdapter


def test_non_following_sse_returns_persisted_events(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    settings = HarnessSettings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        memory_db=tmp_path / "runs" / "memory.sqlite3",
        default_model="fake-model",
    )
    runner = HarnessRunner(
        settings,
        adapter_factory=lambda root, input_path, report_path: FakeLegacyAdapter(
            root, input_path, report_path
        ),
    )
    state = runner.create_run(source)
    monkeypatch.setattr(api_module, "settings", settings)

    async def consume() -> str:
        response = await api_module.stream_events(state.run_id, after=0, follow=False)
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    payload = asyncio.run(consume())
    assert "run.created" in payload
    assert "text/event-stream" in str(
        asyncio.run(api_module.stream_events(state.run_id, after=0, follow=False)).media_type
    )


def test_dashboard_metrics_and_upload_boundary() -> None:
    client = TestClient(api_module.app)
    assert client.get("/").status_code == 200
    assert client.get("/metrics").status_code == 200
    response = client.post(
        "/v1/uploads",
        json={"filename": "payload.exe", "content_base64": "eA=="},
    )
    assert response.status_code == 415
