from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from sensecllm.chat import ReportChatService
from sensecllm.config import HarnessSettings
from sensecllm.harness.checkpoint import CheckpointStore
from sensecllm.harness.runner import HarnessRunner
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.observability.metrics import collect_metrics, prometheus_metrics
from sensecllm.ui import dashboard

settings = HarnessSettings()
runner = HarnessRunner(settings)
memory = EpisodicMemoryStore(settings.memory_db)
app = FastAPI(title="SenseCLLM Harness", version="0.1.0")


class RunRequest(BaseModel):
    input_path: str
    model: str | None = None
    profile: str = Field(pattern="^(full|single_agent|no_memory|no_critic)$", default="full")


class VerificationRequest(BaseModel):
    vulnerability_name: str
    outcome: str = Field(pattern="^(confirmed|rejected|inconclusive|not_tested)$")
    mechanism_name: str = ""
    notes: str = ""
    evidence: str = ""


class HumanDecisionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|revise)$")
    comments: str = ""
    revised_vulnerabilities: list[dict] | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class UploadRequest(BaseModel):
    filename: str
    content_base64: str
    model: str | None = None


def _run_dir(run_id: str) -> Path:
    if not run_id or any(character not in "0123456789abcdef" for character in run_id.casefold()):
        raise HTTPException(status_code=404, detail="run not found")
    return settings.runs_dir.expanduser().resolve() / run_id


def _checkpoint_path(run_id: str) -> Path:
    checkpoint = _run_dir(run_id) / "checkpoint.json"
    if not checkpoint.exists():
        raise HTTPException(status_code=404, detail="run not found")
    return checkpoint


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def ui() -> HTMLResponse:
    return dashboard()


@app.get("/v1/metrics")
def metrics() -> dict:
    return collect_metrics(settings.runs_dir)


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus() -> str:
    return prometheus_metrics(collect_metrics(settings.runs_dir))


@app.post("/v1/runs", status_code=202)
def create_run(request: RunRequest, background: BackgroundTasks) -> dict:
    try:
        run_runner = HarnessRunner(settings, profile=request.profile)
        state = run_runner.create_run(Path(request.input_path), request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background.add_task(run_runner.execute, state)
    return state.to_dict()


@app.post("/v1/uploads", status_code=202)
def upload_and_run(request: UploadRequest, background: BackgroundTasks) -> dict:
    suffix = Path(request.filename).suffix.casefold()
    if suffix not in {".pdf", ".md", ".txt"}:
        raise HTTPException(status_code=415, detail="only PDF, Markdown, and text are supported")
    try:
        content = base64.b64decode(request.content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="invalid base64 content") from exc
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file must be between 1 byte and 15 MiB")
    upload_dir = settings.runs_dir.expanduser().resolve() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(content)
    state = runner.create_run(path, request.model)
    background.add_task(runner.execute, state)
    return state.to_dict()


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return CheckpointStore().load(_checkpoint_path(run_id)).to_dict()


@app.post("/v1/runs/{run_id}/cancel", status_code=202)
def cancel_run(run_id: str) -> dict[str, str]:
    _checkpoint_path(run_id)
    runner.request_cancel(run_id)
    return {"run_id": run_id, "status": "cancel_requested"}


@app.post("/v1/runs/{run_id}/decision", status_code=202)
def decide_run(
    run_id: str,
    request: HumanDecisionRequest,
    background: BackgroundTasks,
) -> dict:
    _checkpoint_path(run_id)
    try:
        state = runner.apply_human_decision(
            run_id,
            request.action,
            request.comments,
            request.revised_vulnerabilities,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if request.action in {"approve", "revise"}:
        background.add_task(runner.execute, state)
    return state.to_dict()


@app.get("/v1/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    root = settings.runs_dir.expanduser().resolve()
    states = []
    for checkpoint in sorted(
        root.glob("*/checkpoint.json"), key=lambda item: item.stat().st_mtime, reverse=True
    )[:limit]:
        try:
            states.append(CheckpointStore().load(checkpoint).to_dict())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return states


@app.get("/v1/compare")
def compare_runs(run_ids: str) -> list[dict]:
    identifiers = [item.strip() for item in run_ids.split(",") if item.strip()][:8]
    if len(identifiers) < 2:
        raise HTTPException(status_code=400, detail="at least two run_ids are required")
    result = []
    for run_id in identifiers:
        state = CheckpointStore().load(_checkpoint_path(run_id))
        usage = state.metadata.get("usage", {})
        result.append(
            {
                "run_id": state.run_id,
                "status": state.status.value,
                "model": state.model,
                "critic_decision": state.metadata.get("critic_decision"),
                "tokens": usage.get("total_tokens", 0),
                "execution_seconds": usage.get("execution_seconds", 0),
                "agent_attempts": usage.get("total_agent_attempts", 0),
                "artifacts": len(state.artifacts),
            }
        )
    return result


@app.get("/v1/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    after: int = Query(default=0, ge=0),
    follow: bool = True,
) -> StreamingResponse:
    run_dir = _run_dir(run_id)
    _checkpoint_path(run_id)
    event_path = run_dir / "events.jsonl"

    async def generate() -> AsyncIterator[str]:
        offset = after
        idle_ticks = 0
        while True:
            emitted = False
            if event_path.exists():
                with event_path.open("r", encoding="utf-8") as handle:
                    handle.seek(offset)
                    while line := handle.readline():
                        offset = handle.tell()
                        emitted = True
                        yield f"id: {offset}\nevent: harness\ndata: {line.strip()}\n\n"
            if not follow:
                break
            checkpoint = CheckpointStore().load(run_dir / "checkpoint.json")
            if (
                checkpoint.status.value
                in {
                    "completed",
                    "failed",
                    "cancelled",
                    "waiting_approval",
                    "rejected",
                }
                and not emitted
            ):
                break
            idle_ticks = 0 if emitted else idle_ticks + 1
            if idle_ticks >= 60:
                yield ": keep-alive\n\n"
                idle_ticks = 0
            await asyncio.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/runs/{run_id}/artifacts/{artifact_name}")
def download_artifact(run_id: str, artifact_name: str) -> FileResponse:
    state = CheckpointStore().load(_checkpoint_path(run_id))
    raw_path = state.artifacts.get(artifact_name)
    if not raw_path:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = Path(raw_path).resolve()
    try:
        path.relative_to(Path(state.run_dir).resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="artifact outside run directory") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path)


@app.get("/v1/memory/cases")
def search_cases(
    q: str = "",
    sensor_type: str = "",
    mechanism: str = "",
    outcome: str = "",
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    return memory.search_cases(
        q,
        sensor_type=sensor_type,
        mechanism=mechanism,
        verification_outcome=outcome,
        limit=limit,
    )


@app.get("/v1/memory/cases/{case_id}")
def get_case(case_id: str) -> dict:
    case = memory.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@app.post("/v1/memory/cases/{case_id}/verification", status_code=201)
def record_verification(case_id: str, request: VerificationRequest) -> dict[str, str]:
    try:
        result_id = memory.record_verification(
            case_id,
            request.vulnerability_name,
            request.outcome,
            mechanism_name=request.mechanism_name,
            notes=request.notes,
            evidence=request.evidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"verification_result_id": result_id}


@app.get("/v1/runs/{run_id}/messages")
def list_messages(run_id: str) -> list[dict]:
    _checkpoint_path(run_id)
    return memory.list_messages(run_id)


@app.post("/v1/runs/{run_id}/chat")
def report_chat(run_id: str, request: ChatRequest) -> dict:
    state = CheckpointStore().load(_checkpoint_path(run_id))
    return ReportChatService(memory).ask(state, request.question)
