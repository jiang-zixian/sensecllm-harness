from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"Bearer\s+sk-[A-Za-z0-9_-]{16,}", re.IGNORECASE),
)
EXCLUDED_PARTS = {".git", ".venv", "RAG_data", ".rag_index", "runs"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".example"}


def main() -> int:
    findings: list[str] = []
    for path in Path.cwd().rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(str(path))
    if findings:
        print("Potential embedded credentials found:", *findings, sep="\n- ")
        return 1
    print("No embedded sk-style credentials found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
