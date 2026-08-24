from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"Bearer\s+(?!sk-(?:xxx|example))[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    re.compile(
        r"(?:api[_-]?key|auth[_-]?header|access[_-]?token|secret)\s*[:=]\s*"
        r"['\"](?!test-|your-|example|placeholder)([^'\"]{20,})['\"]",
        re.IGNORECASE,
    ),
)
EXCLUDED_PARTS = {".git", ".venv", "RAG_data", ".rag_index", "runs"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".json", ".example"}
BINARY_SUFFIXES = {".pyc"}
BINARY_PATTERNS = (
    re.compile(rb"Bearer\s+(?!sk-(?:xxx|example))[A-Za-z0-9._-]{20,}", re.IGNORECASE),
)


def main() -> int:
    findings: list[str] = []
    for path in Path.cwd().rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES | BINARY_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.suffix in BINARY_SUFFIXES:
            if any(pattern.search(path.read_bytes()) for pattern in BINARY_PATTERNS):
                findings.append(str(path))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(str(path))
    if findings:
        print("Potential embedded credentials found:", *findings, sep="\n- ")
        return 1
    print("No embedded provider credentials found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
