from __future__ import annotations

import os
from typing import Any, Dict, List

from .constants import STATUS_FALSE, STATUS_TRUE, STATUS_UNKNOWN


class ParameterConstraintChecker:
    def check(self, constraints: List[Dict[str, Any]]) -> str:
        if os.getenv("SENSECLLM_CONSTRAINTS_ENABLED", "true").casefold() in {
            "0",
            "false",
            "no",
            "off",
        }:
            return STATUS_TRUE
        if not constraints:
            return STATUS_TRUE
        saw_unknown = False
        for constraint in constraints:
            status = constraint.get("status") or constraint.get("current_status")
            if status == STATUS_FALSE:
                return STATUS_FALSE
            if status in {None, "", STATUS_UNKNOWN}:
                saw_unknown = True
        return STATUS_UNKNOWN if saw_unknown else STATUS_TRUE
