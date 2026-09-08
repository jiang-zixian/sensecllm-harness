"""Compare the production grounding prompt with a minimally constrained baseline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sensor_rag.config import PROJECT_ROOT, RAGConfig
from sensor_rag.pipeline import SYSTEM_PROMPT, SensorRAG


ANSWERABLE = [
    "What type of attack and defense does the @PAD paper study?",
    "What privacy and security topic does the Amazon Echo paper investigate?",
    "What waveform is proposed to mitigate FMCW radar spoofing?",
    "What analysis method is used against inaudible ultrasound attacks?",
    "What kind of applications are examined by the smart-home assistant security vetting case study?",
]

UNANSWERABLE = [
    "What was the exact 2031 retail price of the fictional Sensor ZX-999?",
    "Who won the 2035 Nobel Prize in Physics and what sensor did they patent?",
    "Give the launch date and battery capacity of the nonexistent Echo Quantum 12.",
    "What exact CVE number was assigned in 2030 to the fictional RadarFoo vulnerability?",
    "State the measured accuracy of the nonexistent MoonRAG-v9 model on this paper corpus.",
]

REFUSAL = re.compile(
    r"insufficient|not (?:available|provided|found|contain|state|specified)|cannot (?:determine|answer|verify)|"
    r"no (?:evidence|information|relevant|real-world|product|valid|measured|accuracy)|"
    r"does not (?:provide|contain|exist)|unable to|fictional|nonexistent|not yet occurred|"
    r"no accuracy data can be reported|not referenced",
    re.IGNORECASE,
)


def citations(text: str) -> list[int]:
    return [int(value) for value in re.findall(r"\[S(\d+)\]", text)]


def valid_citations(text: str, source_count: int) -> bool:
    values = citations(text)
    return bool(values) and all(1 <= value <= source_count for value in values)


def baseline_chat(rag: SensorRAG, question: str, evidence: str) -> str:
    response = rag.client._post(
        "chat/completions",
        {
            "model": rag.config.generation_model,
            "messages": [
                {"role": "system", "content": "Answer the user's question helpfully."},
                {"role": "user", "content": f"Question:\n{question}\n\nSearch results:\n{evidence}"},
            ],
            "stream": False,
            "max_tokens": 700,
            "temperature": 0.7,
            "top_p": 0.95,
        },
    )
    return str(response["choices"][0]["message"]["content"]).strip()


def strict_chat(rag: SensorRAG, question: str, evidence: str) -> str:
    return rag.client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question:\n{question}\n\nRetrieved evidence:\n{evidence}\n\nAnswer now."},
        ],
        max_tokens=700,
    )


def main() -> None:
    rag = SensorRAG(RAGConfig())
    rows: list[dict[str, Any]] = []
    for answerable, questions in ((True, ANSWERABLE), (False, UNANSWERABLE)):
        for question in questions:
            _, hits = rag.retrieve(question)
            evidence = rag.evidence_pack(hits)
            strict = strict_chat(rag, question, evidence)
            baseline = baseline_chat(rag, question, evidence)
            rows.append(
                {
                    "question": question,
                    "answerable": answerable,
                    "source_count": len(hits),
                    "strict": {
                        "answer": strict,
                        "refused": bool(REFUSAL.search(strict)),
                        "valid_citations": valid_citations(strict, len(hits)),
                    },
                    "baseline": {
                        "answer": baseline,
                        "refused": bool(REFUSAL.search(baseline)),
                        "valid_citations": valid_citations(baseline, len(hits)),
                    },
                }
            )
    metrics = {}
    for mode in ("strict", "baseline"):
        answerable_rows = [row for row in rows if row["answerable"]]
        unanswerable_rows = [row for row in rows if not row["answerable"]]
        metrics[mode] = {
            "answerable_valid_citation_rate": sum(row[mode]["valid_citations"] for row in answerable_rows) / len(answerable_rows),
            "unanswerable_refusal_rate": sum(row[mode]["refused"] for row in unanswerable_rows) / len(unanswerable_rows),
            "unanswerable_answer_rate_proxy": 1 - sum(row[mode]["refused"] for row in unanswerable_rows) / len(unanswerable_rows),
        }
    result = {
        "benchmark_type": "deterministic refusal/citation proxy; manual factual review still required",
        "metrics": metrics,
        "cases": rows,
    }
    path = PROJECT_ROOT / "experiments" / "rag_interview" / "systematic" / "generation_grounding.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
