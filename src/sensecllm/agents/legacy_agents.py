from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import AgentContext, BaseAgent
from .critic_agent import CriticAgent
from .memory_agent import CaseRecallAgent, CaseRefinementAgent


@dataclass
class LegacyStageAgent(BaseAgent):
    name: str
    depends_on: tuple[str, ...] = ()

    def execute(self, context: AgentContext) -> Any:
        return context.runtime.run_stage(self.name, context.state.model)


@dataclass
class SingleAgentBaseline(BaseAgent):
    """A reproducible monolithic baseline for multi-Agent ablations."""

    name: str = "single_agent"
    depends_on: tuple[str, ...] = ()

    def execute(self, context: AgentContext) -> Any:
        outputs = []
        for stage in ("document", "mechanism", "vulnerability", "experiment", "defense"):
            outputs.append(context.runtime.run_stage(stage, context.state.model))
        return {"stages": outputs}


def build_legacy_agents(profile: str = "full") -> list[BaseAgent]:
    """Wrap the existing core without changing its domain implementation."""
    if profile == "single_agent":
        return [SingleAgentBaseline()]
    if profile not in {"full", "no_memory", "no_critic"}:
        raise ValueError(f"unknown Agent profile: {profile}")
    case_memory = profile != "no_memory"
    critic = profile != "no_critic"
    agents: list[BaseAgent] = [LegacyStageAgent("document")]
    if case_memory:
        agents.append(CaseRecallAgent())
    agents.append(LegacyStageAgent("mechanism", ("case_recall",) if case_memory else ("document",)))
    if case_memory:
        agents.append(CaseRefinementAgent())
    agents.append(
        LegacyStageAgent("vulnerability", ("case_refinement",) if case_memory else ("mechanism",))
    )
    if critic:
        agents.append(CriticAgent())
    agents.extend(
        [
            LegacyStageAgent("experiment", ("critic",) if critic else ("vulnerability",)),
            LegacyStageAgent("defense", ("experiment",)),
        ]
    )
    return agents
