from __future__ import annotations

from pathlib import Path

import pytest

from sensecllm.legacy_subprocess import LegacySubprocessAdapter


def test_subprocess_adapter_persists_stage_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    adapter = LegacySubprocessAdapter(tmp_path, source, tmp_path / "run" / "report.md")

    class FakeProcess:
        returncode = 0

        def __init__(self, _command, **kwargs):
            kwargs["stdout"].write("stage output\n")

        def poll(self):
            return self.returncode

    monkeypatch.setattr("subprocess.Popen", FakeProcess)
    result = adapter.run_stage("document", "deepseek-v3.2")

    log_path = Path(str(result["log_path"]))
    assert result["returncode"] == 0
    assert log_path.read_text(encoding="utf-8") == "stage output\n"


def test_subprocess_adapter_surfaces_failed_log_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sensor.md"
    source.write_text("sensor", encoding="utf-8")
    adapter = LegacySubprocessAdapter(tmp_path, source, tmp_path / "run" / "report.md")

    class FakeProcess:
        returncode = 2

        def __init__(self, _command, **kwargs):
            kwargs["stdout"].write("useful failure detail\n")

        def poll(self):
            return self.returncode

    monkeypatch.setattr("subprocess.Popen", FakeProcess)

    with pytest.raises(RuntimeError, match="useful failure detail"):
        adapter.run_stage("mechanism", "deepseek-v3.2")
