from __future__ import annotations

from typing import Any, Dict, List

from .constants import STATUS_FALSE, STATUS_TRUE, STATUS_UNKNOWN


class EvidenceScopeChecker:
    def check_preconditions(self, preconditions: List[Dict[str, Any]]) -> str:
        saw_unknown = False
        for item in preconditions or []:
            status = item.get("current_status")
            scope = item.get("required_evidence_scope")
            if status == STATUS_FALSE:
                return STATUS_FALSE
            if status == STATUS_UNKNOWN:
                saw_unknown = True
            if scope == "target_specific" and status not in {STATUS_TRUE, STATUS_FALSE, STATUS_UNKNOWN}:
                saw_unknown = True
        return STATUS_UNKNOWN if saw_unknown else STATUS_TRUE

    def component_evidence_status(self, component_exists: bool) -> str:
        return STATUS_TRUE if component_exists else STATUS_FALSE

