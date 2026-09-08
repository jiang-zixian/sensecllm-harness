from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sensecllm.agents.base import AgentContext, BaseAgent
from sensecllm.agents.legacy_agents import build_legacy_agents
from sensecllm.config import HarnessSettings
from sensecllm.legacy_subprocess import LegacySubprocessAdapter
from sensecllm.memory.episodic import EpisodicMemoryStore
from sensecllm.observability.tracing import TraceRecorder
from sensecllm.observability.usage import summarize_usage

from .checkpoint import CheckpointStore
from .errors import RunBudgetExceeded, RunCancelled
from .events import EventBus, HarnessEvent
from .failures import FailureClass, classify_failure
from .state import RunState, RunStatus, StageRecord, StageStatus, utc_now

AdapterFactory = Callable[[Path, Path, Path], Any]


class HarnessRunner:
    """Supervisor for the existing domain pipeline.

    Each legacy stage is isolated in a subprocess by default, so concurrent
    runs cannot contaminate one another through legacy module globals.
    """

    def __init__(
        self,
        settings: HarnessSettings | None = None,
        *,
        agents: list[BaseAgent] | None = None,
        adapter_factory: AdapterFactory | None = None,
        memory: EpisodicMemoryStore | None = None,
        profile: str = "full",
    ) -> None:
        self.settings = settings or HarnessSettings()
        self.settings.ensure_directories()
        self.profile = profile
        self.agents = agents or build_legacy_agents(profile)
        self.adapter_factory = adapter_factory or (
            lambda root, input_path, report_path: LegacySubprocessAdapter(
                root,
                input_path,
                report_path,
                timeout_seconds=self.settings.agent_timeout_seconds,
            )
        )
        self.checkpoints = CheckpointStore()
        self.memory = memory or EpisodicMemoryStore(self.settings.memory_db)

    def create_run(
        self, input_path: Path, model: str | None = None
    ) -> RunState:
        source = input_path.expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"input does not exist: {source}")
        run_id = uuid.uuid4().hex
        run_dir = self.settings.runs_dir.expanduser().resolve() / run_id
        report_path = run_dir / "report.md"
        state = RunState(
            run_id=run_id,
            input_path=str(source),
            run_dir=str(run_dir),
            report_path=str(report_path),
            model=model or self.settings.default_model,
            stages={agent.name: StageRecord(agent.name) for agent in self.agents},
            metadata={
                "experiment_config": {
                    "agent_profile": self.profile,
                    "orchestrator": self.settings.orchestrator,
                    "rag_enabled": os.getenv("SENSECLLM_RAG_ENABLED", "true").casefold()
                    not in {"0", "false", "no", "off"},
                    "constraints_enabled": os.getenv(
                        "SENSECLLM_CONSTRAINTS_ENABLED", "true"
                    ).casefold()
                    not in {"0", "false", "no", "off"},
                    "critic_enabled": self.settings.critic_enabled
                    and self.profile not in {"no_critic", "single_agent"},
                },
                "budget": {
                    "run_timeout_seconds": self.settings.run_timeout_seconds,
                    "max_agent_attempts": self.settings.max_agent_attempts,
                    "max_total_agent_attempts": self.settings.max_total_agent_attempts,
                    "max_model_tokens": self.settings.max_model_tokens,
                    "max_estimated_cost": self.settings.max_estimated_cost or None,
                },
                "usage": {
                    "total_agent_attempts": 0,
                    "retry_count": 0,
                    "execution_seconds": 0.0,
                },
            },
        )
        run_dir.mkdir(parents=True, exist_ok=False)
        self.checkpoints.save(state)
        EventBus(run_dir / "events.jsonl").emit(HarnessEvent("run.created", run_id))
        return state

    def run(self, input_path: Path, model: str | None = None) -> RunState:
        return self.execute(self.create_run(input_path, model))

    def resume(self, checkpoint: Path) -> RunState:
        state = self.checkpoints.load(checkpoint.expanduser().resolve())
        if state.status == RunStatus.COMPLETED:
            return state
        for record in state.stages.values():
            if record.status in {
                StageStatus.RUNNING,
                StageStatus.FAILED,
                StageStatus.CANCELLED,
            }:
                record.status = StageStatus.PENDING
                record.error = None
        state.error = None
        cancel_path = Path(state.run_dir) / "cancel.requested"
        if cancel_path.exists():
            cancel_path.unlink()
        return self.execute(state)

    def request_cancel(self, run_id: str) -> Path:
        run_dir = self.settings.runs_dir.expanduser().resolve() / run_id
        if not (run_dir / "checkpoint.json").exists():
            raise FileNotFoundError(f"run does not exist: {run_id}")
        cancel_path = run_dir / "cancel.requested"
        cancel_path.write_text(utc_now(), encoding="utf-8")
        EventBus(run_dir / "events.jsonl").emit(HarnessEvent("run.cancel_requested", run_id))
        return cancel_path

    def apply_human_decision(
        self,
        run_id: str,
        action: str,
        comments: str = "",
        revised_vulnerabilities: list[dict[str, Any]] | None = None,
    ) -> RunState:
        checkpoint_path = self.settings.runs_dir.expanduser().resolve() / run_id / "checkpoint.json"
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"run does not exist: {run_id}")
        state = self.checkpoints.load(checkpoint_path)
        if state.status != RunStatus.WAITING_APPROVAL:
            raise ValueError(f"run is not waiting for approval: {state.status.value}")
        if action not in {"approve", "reject", "revise"}:
            raise ValueError("action must be approve, reject, or revise")
        if action == "revise" and not revised_vulnerabilities:
            raise ValueError("revised_vulnerabilities is required for revise")

        state.metadata["human_decision"] = {
            "action": action,
            "comments": comments,
            "decided_at": utc_now(),
        }
        state.current_stage = None
        if action == "reject":
            state.status = RunStatus.REJECTED
            state.error = "rejected by human reviewer"
            event = "run.rejected"
        elif action == "revise":
            target = state.data_dir / "step3_vulnerability_items.json"
            target.write_text(
                __import__("json").dumps(
                    revised_vulnerabilities, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
            critic = state.stages.get("critic")
            if critic:
                critic.status = StageStatus.PENDING
                critic.error = None
                critic.completed_at = None
            state.status = RunStatus.PENDING
            state.error = None
            state.metadata["requires_human_review"] = False
            event = "run.revised"
        else:
            state.status = RunStatus.PENDING
            state.error = None
            state.metadata["requires_human_review"] = False
            event = "run.approved"
        self.checkpoints.save(state)
        EventBus(Path(state.run_dir) / "events.jsonl").emit(
            HarnessEvent(event, state.run_id, data={"comments": comments})
        )
        return state

    def recover_stale_runs(self, older_than_seconds: int = 300) -> list[RunState]:
        recovered: list[RunState] = []
        now = time.time()
        root = self.settings.runs_dir.expanduser().resolve()
        for checkpoint_path in root.glob("*/checkpoint.json"):
            if now - checkpoint_path.stat().st_mtime < older_than_seconds:
                continue
            try:
                state = self.checkpoints.load(checkpoint_path)
            except (OSError, ValueError):
                continue
            if state.status != RunStatus.RUNNING:
                continue
            state.status = RunStatus.FAILED
            state.error = "interrupted: stale running checkpoint recovered"
            if state.current_stage and state.current_stage in state.stages:
                record = state.stages[state.current_stage]
                record.status = StageStatus.FAILED
                record.error = state.error
                record.failure_class = FailureClass.TRANSIENT.value
            self.checkpoints.save(state)
            EventBus(Path(state.run_dir) / "events.jsonl").emit(
                HarnessEvent("run.stale_recovered", state.run_id, state.current_stage)
            )
            recovered.append(state)
        return recovered

    def execute(self, state: RunState) -> RunState:
        session_started = time.monotonic()
        previous_elapsed = float(
            state.metadata.setdefault("usage", {}).get("execution_seconds", 0.0)
        )
        event_bus = EventBus(Path(state.run_dir) / "events.jsonl")
        runtime = self.adapter_factory(
            self.settings.project_root,
            Path(state.input_path),
            Path(state.report_path),
        )
        state.status = RunStatus.RUNNING
        self.checkpoints.save(state)
        event_bus.emit(HarnessEvent("run.started", state.run_id))

        try:
            if self.settings.orchestrator == "langgraph":
                from sensecllm.harness.langgraph_executor import LangGraphAgentExecutor

                LangGraphAgentExecutor(self, self.agents).run(
                    state,
                    runtime,
                    event_bus,
                    session_started=session_started,
                    previous_elapsed=previous_elapsed,
                )
                if state.status in {
                    RunStatus.REJECTED,
                    RunStatus.WAITING_APPROVAL,
                }:
                    return state
                return self._complete_run(
                    state, event_bus, session_started, previous_elapsed
                )
            return self._execute_sequential(
                state, runtime, event_bus, session_started, previous_elapsed
            )
        except RunCancelled as exc:
            state.status = RunStatus.CANCELLED
            state.error = str(exc)
            self._update_elapsed(state, session_started, previous_elapsed)
            self._update_model_usage(state)
            self.checkpoints.save(state)
            event_bus.emit(HarnessEvent("run.cancelled", state.run_id, state.current_stage))
            return state
        except Exception as exc:
            state.status = RunStatus.FAILED
            state.error = f"{type(exc).__name__}: {exc}"
            self._update_elapsed(state, session_started, previous_elapsed)
            self._update_model_usage(state)
            self.checkpoints.save(state)
            event_bus.emit(
                HarnessEvent(
                    "run.failed", state.run_id, state.current_stage, data={"error": state.error}
                )
            )
            raise

    def _execute_sequential(
        self,
        state: RunState,
        runtime: Any,
        event_bus: EventBus,
        session_started: float,
        previous_elapsed: float,
    ) -> RunState:
        for agent in self.agents:
            self._check_run_budget(state, session_started, previous_elapsed)
            if (Path(state.run_dir) / "cancel.requested").exists():
                raise RunCancelled("run cancellation requested")
            record = state.stages[agent.name]
            if record.status == StageStatus.COMPLETED:
                continue
            self._ensure_dependencies(state, agent)
            self._execute_agent(agent, state, runtime, event_bus)
            if self._handle_post_agent_route(
                agent, state, event_bus, session_started, previous_elapsed
            ):
                return state
        return self._complete_run(state, event_bus, session_started, previous_elapsed)

    def _complete_run(
        self,
        state: RunState,
        event_bus: EventBus,
        session_started: float,
        previous_elapsed: float,
    ) -> RunState:
        state.status = RunStatus.COMPLETED
        state.current_stage = None
        state.artifacts = self._discover_artifacts(state)
        case_id = self.memory.remember_run(state)
        state.metadata["episodic_case_id"] = case_id
        self._update_elapsed(state, session_started, previous_elapsed)
        self._update_model_usage(state)
        self.checkpoints.save(state)
        event_bus.emit(HarnessEvent("run.completed", state.run_id, data={"case_id": case_id}))
        return state

    def _handle_post_agent_route(
        self,
        agent: BaseAgent,
        state: RunState,
        event_bus: EventBus,
        session_started: float,
        previous_elapsed: float,
    ) -> str | None:
        if agent.name == "critic" and state.metadata.get("critic_decision") == "reject":
            state.status = RunStatus.REJECTED
            state.error = "rejected by critic"
            state.current_stage = None
            self._update_elapsed(state, session_started, previous_elapsed)
            self._update_model_usage(state)
            self.checkpoints.save(state)
            event_bus.emit(HarnessEvent("run.rejected", state.run_id))
            return "rejected"
        if agent.name == "critic" and state.metadata.get("requires_human_review"):
            state.status = RunStatus.WAITING_APPROVAL
            state.current_stage = None
            self._update_elapsed(state, session_started, previous_elapsed)
            self._update_model_usage(state)
            self.checkpoints.save(state)
            event_bus.emit(HarnessEvent("run.waiting_approval", state.run_id))
            return "waiting_approval"
        return None

    def _execute_agent(
        self,
        agent: BaseAgent,
        state: RunState,
        runtime: Any,
        event_bus: EventBus,
    ) -> None:
        record = state.stages[agent.name]
        state.current_stage = agent.name
        record.status = StageStatus.RUNNING
        record.started_at = utc_now()
        self.checkpoints.save(state)
        event_bus.emit(HarnessEvent("agent.started", state.run_id, agent.name))
        while True:
            try:
                self._check_attempt_budget(state)
                record.attempts += 1
                usage = state.metadata.setdefault("usage", {})
                usage["total_agent_attempts"] = int(usage.get("total_agent_attempts", 0)) + 1
                output = agent.execute(
                    AgentContext(
                        state=state,
                        runtime=runtime,
                        memory=self.memory,
                        settings=self.settings,
                    )
                )
                record.output_preview = str(output)[:500]
                record.status = StageStatus.COMPLETED
                record.completed_at = utc_now()
                record.error = None
                record.failure_class = None
                self._record_agent_span(state, record)
                self._update_model_usage(state)
                self.checkpoints.save(state)
                event_bus.emit(HarnessEvent("agent.completed", state.run_id, agent.name))
                return
            except RunCancelled:
                record.status = StageStatus.CANCELLED
                record.completed_at = utc_now()
                record.error = "run cancellation requested"
                record.failure_class = FailureClass.CANCELLED.value
                self._record_agent_span(state, record)
                self.checkpoints.save(state)
                event_bus.emit(HarnessEvent("agent.cancelled", state.run_id, agent.name))
                raise
            except Exception as exc:
                failure_class = classify_failure(exc)
                record.error = f"{type(exc).__name__}: {exc}"
                record.failure_class = failure_class.value
                retryable = failure_class in {
                    FailureClass.TRANSIENT,
                    FailureClass.TIMEOUT,
                }
                if retryable and record.attempts < self.settings.max_agent_attempts:
                    usage = state.metadata.setdefault("usage", {})
                    usage["retry_count"] = int(usage.get("retry_count", 0)) + 1
                    self.checkpoints.save(state)
                    event_bus.emit(
                        HarnessEvent(
                            "agent.retrying",
                            state.run_id,
                            agent.name,
                            data={
                                "attempt": record.attempts,
                                "failure_class": failure_class.value,
                                "error": record.error,
                            },
                        )
                    )
                    delay = self.settings.retry_backoff_seconds * (2 ** (record.attempts - 1))
                    time.sleep(delay)
                    continue
                record.status = StageStatus.FAILED
                record.completed_at = utc_now()
                self._record_agent_span(state, record)
                self.checkpoints.save(state)
                event_bus.emit(
                    HarnessEvent(
                        "agent.failed",
                        state.run_id,
                        agent.name,
                        data={
                            "error": record.error,
                            "failure_class": failure_class.value,
                            "attempts": record.attempts,
                        },
                    )
                )
                raise

    def _check_attempt_budget(self, state: RunState) -> None:
        attempts = int(state.metadata.setdefault("usage", {}).get("total_agent_attempts", 0))
        if attempts >= self.settings.max_total_agent_attempts:
            raise RunBudgetExceeded(
                f"total agent attempt budget exhausted: {attempts}/"
                f"{self.settings.max_total_agent_attempts}"
            )

    def _check_run_budget(
        self, state: RunState, session_started: float, previous_elapsed: float
    ) -> None:
        elapsed = previous_elapsed + (time.monotonic() - session_started)
        if elapsed > self.settings.run_timeout_seconds:
            raise RunBudgetExceeded(
                f"run time budget exceeded: {elapsed:.1f}s/{self.settings.run_timeout_seconds}s"
            )
        usage = state.metadata.setdefault("usage", {})
        tokens = int(usage.get("total_tokens", 0))
        if self.settings.max_model_tokens > 0 and tokens > self.settings.max_model_tokens:
            raise RunBudgetExceeded(
                f"model token budget exceeded: {tokens}/{self.settings.max_model_tokens}"
            )
        cost = usage.get("estimated_cost")
        if (
            self.settings.max_estimated_cost > 0
            and cost is not None
            and float(cost) > self.settings.max_estimated_cost
        ):
            raise RunBudgetExceeded(
                f"estimated cost budget exceeded: {cost}/{self.settings.max_estimated_cost}"
            )

    @staticmethod
    def _update_elapsed(state: RunState, session_started: float, previous_elapsed: float) -> None:
        state.metadata.setdefault("usage", {})["execution_seconds"] = round(
            previous_elapsed + (time.monotonic() - session_started), 3
        )

    @staticmethod
    def _update_model_usage(state: RunState) -> None:
        state.metadata.setdefault("usage", {}).update(
            summarize_usage(Path(state.run_dir) / "usage.jsonl")
        )

    @staticmethod
    def _record_agent_span(state: RunState, record: StageRecord) -> None:
        if not record.started_at or not record.completed_at:
            return
        TraceRecorder(Path(state.run_dir) / "traces.jsonl", state.run_id).record(
            name=f"agent.{record.name}",
            started_at=record.started_at,
            ended_at=record.completed_at,
            status=record.status.value,
            attributes={
                "agent": record.name,
                "attempts": record.attempts,
                "failure_class": record.failure_class,
            },
            error=record.error,
        )

    @staticmethod
    def _ensure_dependencies(state: RunState, agent: BaseAgent) -> None:
        missing = [
            dependency
            for dependency in agent.depends_on
            if state.stages.get(dependency) is None
            or state.stages[dependency].status != StageStatus.COMPLETED
        ]
        if missing:
            raise RuntimeError(
                f"agent {agent.name} has incomplete dependencies: {', '.join(missing)}"
            )

    @staticmethod
    def _discover_artifacts(state: RunState) -> dict[str, str]:
        artifacts: dict[str, str] = {}
        report = Path(state.report_path)
        if report.exists():
            artifacts["report"] = str(report)
        if state.data_dir.exists():
            for path in sorted(state.data_dir.iterdir()):
                if path.is_file():
                    artifacts[path.stem] = str(path)
        log_dir = Path(state.run_dir) / "logs"
        if log_dir.exists():
            for path in sorted(log_dir.glob("*.log")):
                artifacts[f"log_{path.stem}"] = str(path)
        for name in ("checkpoint", "events", "traces", "usage"):
            suffix = ".json" if name == "checkpoint" else ".jsonl"
            path = Path(state.run_dir) / f"{name}{suffix}"
            if path.is_file():
                artifacts[name] = str(path)
        return artifacts

    @staticmethod
    def run_dir(state: RunState) -> Path:
        return Path(state.run_dir)
