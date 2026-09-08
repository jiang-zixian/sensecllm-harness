from __future__ import annotations

from typing import Any


def clean_table_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.replace("\r", "\n").split()).replace("|", "\\|").strip()


def normalize_table_rows(rows: Any) -> list[list[str]]:
    normalized: list[list[str]] = []
    max_width = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, (list, tuple)):
            continue
        cells = [clean_table_cell(cell) for cell in row]
        if any(cells):
            normalized.append(cells)
            max_width = max(max_width, len(cells))
    if max_width < 2 or not normalized:
        return []
    return [row + [""] * (max_width - len(row)) for row in normalized]


def table_to_markdown(rows: Any, *, page_number: int, table_number: int) -> str:
    normalized = normalize_table_rows(rows)
    if not normalized:
        return ""
    header = normalized[0]
    body = normalized[1:] or [[""] * len(header)]
    lines = [
        f"### Page {page_number} Table {table_number}",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)
