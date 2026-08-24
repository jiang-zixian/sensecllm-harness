from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExpectedLabels(BaseModel):
    sensor_type: str = ""
    extraction_fields: dict[str, str] = Field(default_factory=dict)
    mechanisms: list[str] = Field(default_factory=list)
    vulnerabilities: list[str] = Field(default_factory=list)
    relevant_rag_ids: list[str] = Field(default_factory=list)
    rag_relevance: dict[str, float] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    case_id: str
    input_path: str = ""
    split: Literal["train", "dev", "test"] = "test"
    notes: str = ""
    labels: ExpectedLabels


class BenchmarkManifest(BaseModel):
    version: str = "1.0"
    name: str
    cases: list[BenchmarkCase]
