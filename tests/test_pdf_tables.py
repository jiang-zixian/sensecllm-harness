from __future__ import annotations

from sensecllm.pdf_tables import normalize_table_rows, table_to_markdown
from sensor_rag.pdf_ingest import extract_page_tables_markdown, merge_page_text_and_tables


class FakePdfPage:
    def __init__(self, tables):
        self._tables = tables

    def extract_tables(self):
        return self._tables


def test_table_rows_normalize_and_escape_cells() -> None:
    rows = normalize_table_rows(
        [
            ["Parameter", "Value"],
            ["Voltage", "3.3 | 5 V"],
            [None, "ignored empty name"],
        ]
    )

    assert rows == [
        ["Parameter", "Value"],
        ["Voltage", "3.3 \\| 5 V"],
        ["", "ignored empty name"],
    ]


def test_table_to_markdown_adds_header_separator() -> None:
    markdown = table_to_markdown(
        [["Parameter", "Value"], ["Frequency", "40 kHz"]],
        page_number=2,
        table_number=1,
    )

    assert "### Page 2 Table 1" in markdown
    assert "| Parameter | Value |" in markdown
    assert "| --- | --- |" in markdown
    assert "| Frequency | 40 kHz |" in markdown


def test_rag_pdf_ingest_merges_extracted_tables_into_page_text() -> None:
    table_blocks = extract_page_tables_markdown(
        FakePdfPage([[["Limit", "Value"], ["Noise", "35 dB"]]]),
        page_number=4,
    )
    merged = merge_page_text_and_tables("Electrical characteristics", table_blocks)

    assert "Electrical characteristics" in merged
    assert "## Extracted tables" in merged
    assert "| Limit | Value |" in merged
    assert "| Noise | 35 dB |" in merged
