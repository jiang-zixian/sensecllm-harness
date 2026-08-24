from __future__ import annotations

from typing import Any, Dict


class FinalPathSummarizer:
    def summarize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        summaries = []
        for path in payload.get("accepted_paths", []):
            mechanisms = path.get("mechanism_instances", [])
            mechanism_text = ", ".join(
                f"{item.get('mechanism_name')} at {item.get('source_component')}" for item in mechanisms
            )
            summaries.append(
                {
                    "path_id": path.get("path_id"),
                    "plain_language_summary": (
                        f"{path.get('external_signal', {}).get('description', 'external signal')} reaches "
                        f"{path.get('observable_output', 'an abnormal output')} through {mechanism_text}."
                    ),
                    "mechanism_summaries": [
                        {
                            "mechanism_name": item.get("mechanism_name"),
                            "source_component": item.get("source_component"),
                            "plain_language_analysis": item.get("plain_language_analysis"),
                        }
                        for item in mechanisms
                    ],
                }
            )
        return {"path_summaries": summaries}

