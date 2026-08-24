from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class LegacyPipelineAdapter:
    """Adapter around the unchanged steps-graph-v2 implementation.

    Legacy modules copy input/output configuration at import time. The adapter
    centralises that compatibility behaviour until the core is natively typed.
    HarnessRunner serialises runs because these module globals are process-wide.
    """

    def __init__(self, project_root: Path, input_path: Path, report_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.input_path = input_path.resolve()
        self.report_path = report_path.resolve()
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self._modules = self._load_modules()

    def _load_modules(self) -> dict[str, ModuleType]:
        legacy_dir = self.project_root / "src" / "steps-graph-v2"
        for path in (self.project_root, legacy_dir):
            value = str(path)
            if value not in sys.path:
                sys.path.insert(0, value)

        config = importlib.import_module("helpers.configs.configs")
        config.input_file = self.input_path  # type: ignore[attr-defined]
        config.output_report = self.report_path  # type: ignore[attr-defined]
        config.output_report_cn = self.report_path.with_name(  # type: ignore[attr-defined]
            "report.zh.md"
        )

        names = {
            "temp_paths": "temp_paths",
            "document": "step1_extract",
            "mechanism": "step2_analyze",
            "vulnerability": "step3_detect",
            "experiment": "step4_verify_per_vulnerability",
            "defense": "step5_defense",
        }
        modules = {key: importlib.import_module(value) for key, value in names.items()}
        for module in modules.values():
            if hasattr(module, "input_file"):
                module.input_file = self.input_path  # type: ignore[attr-defined]
            if hasattr(module, "output_report"):
                module.output_report = self.report_path  # type: ignore[attr-defined]
        modules["temp_paths"].output_report = self.report_path  # type: ignore[attr-defined]
        return modules

    def run_stage(self, stage: str, model: str) -> Any:
        if stage == "document":
            return self._modules[stage].run_step_1(model)
        if stage == "mechanism":
            return self._modules[stage].run_step_2(model_for_analyze=model)
        if stage == "vulnerability":
            return self._modules[stage].run_step_3(model_for_detect=model, use_verifier=False)
        if stage == "experiment":
            return self._modules[stage].run_step_4(model_for_verify=model)
        if stage == "defense":
            return self._modules[stage].run_step_5()
        raise ValueError(f"unknown legacy stage: {stage}")
