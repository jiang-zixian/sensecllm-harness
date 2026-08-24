from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from sensecllm.harness.errors import RunCancelled


class LegacySubprocessAdapter:
    """Run each unchanged legacy stage in its own process."""

    def __init__(
        self,
        project_root: Path,
        input_path: Path,
        report_path: Path,
        *,
        timeout_seconds: int = 900,
    ) -> None:
        self.project_root = project_root.resolve()
        self.input_path = input_path.resolve()
        self.report_path = report_path.resolve()
        self.timeout_seconds = timeout_seconds
        self.log_dir = self.report_path.parent / "logs"
        self.cancel_path = self.report_path.parent / "cancel.requested"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run_stage(self, stage: str, model: str) -> dict[str, str | int]:
        log_path = self.log_dir / f"{stage}.log"
        command = [
            sys.executable,
            "-m",
            "sensecllm.legacy_worker",
            stage,
            "--project-root",
            str(self.project_root),
            "--input",
            str(self.input_path),
            "--report",
            str(self.report_path),
            "--model",
            model,
        ]
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH", "")
        paths = [str(self.project_root), str(self.project_root / "src")]
        if existing_pythonpath:
            paths.append(existing_pythonpath)
        environment["PYTHONPATH"] = os.pathsep.join(paths)
        environment["SENSECLLM_USAGE_FILE"] = str(self.report_path.parent / "usage.jsonl")
        environment["SENSECLLM_TRACE_ID"] = self.report_path.parent.name

        if self.cancel_path.exists():
            raise RunCancelled(f"run cancelled before stage {stage}")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            started = time.monotonic()
            while process.poll() is None:
                if self.cancel_path.exists():
                    self._stop(process)
                    raise RunCancelled(f"run cancelled during stage {stage}")
                if time.monotonic() - started > self.timeout_seconds:
                    self._stop(process)
                    raise TimeoutError(
                        f"legacy stage {stage} exceeded {self.timeout_seconds}s; log={log_path}"
                    )
                time.sleep(0.2)
            returncode = process.returncode

        if returncode != 0:
            tail = self._tail(log_path)
            raise RuntimeError(
                f"legacy stage {stage} exited with code {returncode}; log={log_path}; tail={tail}"
            )
        return {"stage": stage, "returncode": returncode, "log_path": str(log_path)}

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _tail(path: Path, lines: int = 20) -> str:
        try:
            return " | ".join(path.read_text(encoding="utf-8").splitlines()[-lines:])
        except OSError:
            return "log unavailable"
