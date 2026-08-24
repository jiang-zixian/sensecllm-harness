from __future__ import annotations

import hashlib
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Iterable

import pdfplumber
from pypdf import PdfReader

from .models import PaperChunk, ParsedPaper


_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_RE = re.compile(r"\n{3,}")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?。！？;；])\s+")


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def discover_pdfs(data_dir: Path) -> list[Path]:
    return sorted(
        (path for path in data_dir.rglob("*.pdf") if path.is_file()),
        key=lambda path: str(path).casefold(),
    )


def _clean_line(line: str) -> str:
    return _SPACE_RE.sub(" ", line).strip()


def _edge_lines(raw_pages: list[str]) -> set[str]:
    """Detect repeated running headers/footers without touching body text."""
    counts: Counter[str] = Counter()
    for text in raw_pages:
        lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
        candidates = set(lines[:3] + lines[-3:])
        counts.update(line.casefold() for line in candidates if 3 <= len(line) <= 160)
    threshold = max(3, int(len(raw_pages) * 0.45))
    return {line for line, count in counts.items() if count >= threshold}


def clean_page_text(text: str, repeated_edges: set[str]) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\x00", "").splitlines():
        line = _clean_line(raw_line)
        if not line or line.casefold() in repeated_edges:
            lines.append("")
            continue
        if re.fullmatch(r"(?:page\s*)?\d{1,4}", line, flags=re.IGNORECASE):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
    text = re.sub(r"(?<![.!?:;。！？：；])\n(?!\n)", " ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _join_words(words: list[dict]) -> str:
    return " ".join(str(word.get("text", "")).strip() for word in words if str(word.get("text", "")).strip())


def _render_lines(lines: list[tuple[float, str]]) -> str:
    if not lines:
        return ""
    gaps = [lines[index][0] - lines[index - 1][0] for index in range(1, len(lines))]
    typical_gap = statistics.median(gap for gap in gaps if gap > 0) if any(gap > 0 for gap in gaps) else 10.0
    output: list[str] = []
    previous_top: float | None = None
    for top, text in lines:
        if previous_top is not None and top - previous_top > max(12.0, typical_gap * 1.55):
            output.append("")
        output.append(text)
        previous_top = top
    return "\n".join(output)


def extract_page_in_reading_order(page) -> str:
    """Recover the common full-width-header + two-column paper reading order."""
    words = page.dedupe_chars().extract_words(
        x_tolerance=2,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=False,
    )
    if not words:
        return ""
    words.sort(key=lambda word: (float(word["top"]), float(word["x0"])))
    grouped: list[list[dict]] = []
    for word in words:
        if not grouped or abs(float(word["top"]) - statistics.median(float(item["top"]) for item in grouped[-1])) > 3.0:
            grouped.append([word])
        else:
            grouped[-1].append(word)

    width = float(page.width)
    middle = width / 2.0
    # IEEE/ACM two-column PDFs often have only an 11-14 pt gutter after cropping.
    min_column_gap = max(8.0, width * 0.015)
    prefix: list[tuple[float, str]] = []
    left: list[tuple[float, str]] = []
    right: list[tuple[float, str]] = []
    split_lines: list[tuple[float, list[dict], list[dict]]] = []
    unsplit_lines: list[tuple[float, list[dict]]] = []

    for line_words in grouped:
        line_words.sort(key=lambda word: float(word["x0"]))
        top = statistics.median(float(word["top"]) for word in line_words)
        best_split: tuple[float, int] | None = None
        for index in range(len(line_words) - 1):
            first = line_words[index]
            second = line_words[index + 1]
            gap = float(second["x0"]) - float(first["x1"])
            if float(first["x1"]) <= middle + width * 0.08 and float(second["x0"]) >= middle - width * 0.08:
                if gap >= min_column_gap and (best_split is None or gap > best_split[0]):
                    best_split = (gap, index)
        if best_split is None:
            unsplit_lines.append((top, line_words))
        else:
            index = best_split[1]
            split_lines.append((top, line_words[: index + 1], line_words[index + 1 :]))

    # A page with only a few apparent splits is usually single-column prose or a table.
    is_two_column = len(split_lines) >= max(4, int(len(grouped) * 0.12))
    if not is_two_column:
        return "\n".join(_join_words(line) for line in grouped)

    first_split_top = min(top for top, _, _ in split_lines)
    for top, line_words in unsplit_lines:
        text = _join_words(line_words)
        x0 = min(float(word["x0"]) for word in line_words)
        x1 = max(float(word["x1"]) for word in line_words)
        center = (x0 + x1) / 2.0
        if top < first_split_top - 3.0 or (x0 < middle < x1 and x1 - x0 > width * 0.62):
            prefix.append((top, text))
        elif center <= middle:
            left.append((top, text))
        else:
            right.append((top, text))
    for top, left_words, right_words in split_lines:
        left.append((top, _join_words(left_words)))
        right.append((top, _join_words(right_words)))

    sections = [_render_lines(sorted(lines)) for lines in (prefix, left, right) if lines]
    return "\n\n".join(section for section in sections if section)


def _split_oversized_unit(unit: str, target: int) -> list[str]:
    sentences = _SENTENCE_END_RE.split(unit)
    if len(sentences) == 1:
        return [unit[start : start + target] for start in range(0, len(unit), target)]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > target:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, target: int, overlap: int) -> list[str]:
    if len(text) <= target:
        return [text] if text else []
    units: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(_split_oversized_unit(paragraph, target))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for unit in units:
        extra = len(unit) + (2 if current else 0)
        if current and current_len + extra > target:
            chunks.append("\n\n".join(current).strip())
            carry: list[str] = []
            carry_len = 0
            for prior in reversed(current):
                if carry and carry_len + len(prior) + 2 > overlap:
                    break
                carry.insert(0, prior)
                carry_len += len(prior) + 2
            current = carry
            current_len = carry_len
        current.append(unit)
        current_len += extra
    if current:
        tail = "\n\n".join(current).strip()
        if not chunks or tail != chunks[-1]:
            chunks.append(tail)
    return [chunk for chunk in chunks if len(chunk) >= 80]


def _collection(relative_path: str) -> str:
    lowered = relative_path.casefold()
    if "strong_related" in lowered:
        return "strong_related_papers"
    if "related_papers" in lowered:
        return "related_papers"
    return "papers"


def _paper_title(reader: PdfReader, path: Path) -> str:
    metadata = reader.metadata
    title = str(getattr(metadata, "title", "") or "").strip() if metadata else ""
    if not title or title.casefold() in {"untitled", "unknown"} or len(title) < 5:
        title = path.stem
    return _SPACE_RE.sub(" ", title).strip()


def parse_pdf(
    path: Path,
    data_dir: Path,
    chunk_chars: int,
    overlap_chars: int,
    known_sha256: str | None = None,
) -> ParsedPaper:
    doc_id = known_sha256 or sha256_file(path)
    relative_path = str(path.relative_to(data_dir))
    warnings: list[str] = []
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise RuntimeError(f"Encrypted PDF cannot be read: {relative_path}") from exc

    raw_pages: list[str] = []
    with pdfplumber.open(str(path), password="") as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            try:
                raw_pages.append(extract_page_in_reading_order(page))
            except Exception as exc:
                warnings.append(f"page {page_number}: {type(exc).__name__}")
                try:
                    raw_pages.append(reader.pages[page_number - 1].extract_text() or "")
                except Exception:
                    raw_pages.append("")

    repeated_edges = _edge_lines(raw_pages)
    title = _paper_title(reader, path)
    collection = _collection(relative_path)
    chunks: list[PaperChunk] = []
    chunk_index = 0
    for page_number, raw_text in enumerate(raw_pages, start=1):
        cleaned = clean_page_text(raw_text, repeated_edges)
        for piece in split_text(cleaned, chunk_chars, overlap_chars):
            chunk_id = f"{doc_id[:20]}:{chunk_index}"
            search_text = f"Paper: {title}\nCollection: {collection}\n{piece}"
            chunks.append(
                PaperChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    source_path=relative_path,
                    title=title,
                    collection=collection,
                    page_start=page_number,
                    page_end=page_number,
                    chunk_index=chunk_index,
                    text=piece,
                    search_text=search_text,
                )
            )
            chunk_index += 1
    if not chunks:
        warnings.append("no extractable text; OCR may be required")
    return ParsedPaper(
        path=path,
        relative_path=relative_path,
        doc_id=doc_id,
        title=title,
        collection=collection,
        page_count=len(raw_pages),
        chunks=chunks,
        warnings=warnings,
    )


def batched(items: list[PaperChunk], size: int) -> Iterable[list[PaperChunk]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
