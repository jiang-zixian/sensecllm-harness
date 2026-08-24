from __future__ import annotations

from typing import Any, Dict, List

from .constants import ALLOWED_MECHANISMS


class Step2LegacyOutputAdapter:
    def adapt(self, mechanism_paths_payload: Dict[str, Any]) -> Dict[str, Any]:
        mechanisms: List[Dict[str, Any]] = []
        mechanism_candidates = mechanism_paths_payload.get("mechanism_candidates")
        if isinstance(mechanism_candidates, list):
            for candidate in mechanism_candidates:
                mechanism_name = candidate.get("mechanism_name")
                if mechanism_name not in ALLOWED_MECHANISMS:
                    continue
                status = candidate.get("status", "")
                mechanisms.append(
                    {
                        "no": len(mechanisms) + 1,
                        "External Signal": {
                            "modality": candidate.get("attack_origin") or candidate.get("input_modality", ""),
                            "description": "Mechanism-level Step2 candidate; a complete observable path is not required.",
                            "parameter_range": "Concrete attack parameters are deferred to later verification.",
                        },
                        "Mechanism Name": mechanism_name,
                        "Source Component": candidate.get("source_component", ""),
                        "Detailed Description and Analysis": candidate.get("plain_language_analysis", ""),
                        "mechanism_name": mechanism_name,
                        "source_component": candidate.get("source_component", ""),
                        "mechanism": candidate.get("plain_language_analysis", ""),
                        "evidence": [
                            {
                                "source": "Step2 Mechanism Edge",
                                "summary": (
                                    f"Derived from non-rejected graph edge {candidate.get('edge_id', '')}; "
                                    f"status={status}."
                                ),
                            }
                        ],
                        "uncertainty score": 0.25 if status == "TRUE" else 0.5,
                        "metadata": {
                            "edge_id": candidate.get("edge_id", ""),
                            "step2_status": status,
                            "requires_followup_verification": candidate.get(
                                "requires_followup_verification",
                                status == "UNKNOWN",
                            ),
                        },
                    }
                )
            return {"mechanisms": mechanisms}

        for path in mechanism_paths_payload.get("accepted_paths", []):
            path_id = path.get("path_id", "")
            external_signal = path.get("external_signal", {})
            for instance in path.get("mechanism_instances", []):
                mechanism_name = instance.get("mechanism_name")
                if mechanism_name not in ALLOWED_MECHANISMS:
                    continue
                source_component = instance.get("source_component", "")
                analysis = instance.get("plain_language_analysis", "")
                mechanisms.append(
                    {
                        "no": len(mechanisms) + 1,
                        "External Signal": {
                            "modality": external_signal.get("modality", ""),
                            "description": external_signal.get("description", ""),
                            "parameter_range": "Qualitative Step2 condition only; concrete attack parameters are deferred to later verification.",
                        },
                        "Mechanism Name": mechanism_name,
                        "Source Component": source_component,
                        "Detailed Description and Analysis": analysis,
                        "mechanism_name": mechanism_name,
                        "source_component": source_component,
                        "mechanism": analysis,
                        "evidence": [
                            {
                                "source": "Step2 Mechanism",
                                "summary": f"Derived from accepted graph path {path_id}; status is physically admissible, not hardware-verified.",
                            }
                        ],
                        "uncertainty score": 0.25,
                        "metadata": {
                            "path_id": path_id,
                            "mechanism_node_id": instance.get("mechanism_node_id", ""),
                            "step2_status": path.get("status", ""),
                        },
                    }
                )
        return {"mechanisms": mechanisms}


def render_legacy_markdown(payload: Dict[str, Any]) -> str:
    rows = payload.get("mechanisms", [])
    if not rows:
        return "### Vulnerability Mechanism Analysis\n\nNo accepted physically admissible mechanism paths.\n"
    lines = [
        "### Vulnerability Mechanism Analysis",
        "",
        "| No. | Mechanism Name | Source Component | Mechanism |",
        "|:---:|:---|:---|:---|",
    ]
    for idx, item in enumerate(rows, start=1):
        mechanism = str(item.get("Detailed Description and Analysis") or item.get("mechanism") or "").replace("|", "\\|")
        source_component = str(item.get("Source Component") or item.get("source_component")).replace("|", "\\|")
        lines.append(
            f"| {idx} | {item.get('Mechanism Name') or item.get('mechanism_name')} | "
            f"{source_component} | {mechanism} |"
        )
    return "\n".join(lines) + "\n"
