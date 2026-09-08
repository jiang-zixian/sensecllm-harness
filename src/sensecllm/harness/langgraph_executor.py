from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from sensecllm.harness.errors import RunCancelled
from sensecllm.harness.events import EventBus
from sensecllm.harness.state import RunState, StageStatus

if TYPE_CHECKING:
    from sensecllm.agents.base import BaseAgent
    from sensecllm.harness.runner import HarnessRunner


class AgentGraphState(TypedDict, total=False):
    state: RunState
    runtime: Any
    event_bus: EventBus
    session_started: float
    previous_elapsed: float
    stop_reason: str | None


class LangGraphAgentExecutor:
    """Run the existing BaseAgent DAG through LangGraph nodes and edges."""

    def __init__(self, runner: HarnessRunner, agents: list[BaseAgent]) -> None:
        self.runner = runner
        self.agents = agents

    def run(
        self,
        state: RunState,
        runtime: Any,
        event_bus: EventBus,
        *,
        session_started: float,
        previous_elapsed: float,
    ) -> AgentGraphState:
        if not self.agents:
            return {"state": state, "stop_reason": None}

        graph = StateGraph(AgentGraphState)
        for agent in self.agents:
            graph.add_node(agent.name, self._node(agent))

        graph.add_edge(START, self.agents[0].name)
        for index, agent in enumerate(self.agents):
            next_agent = self.agents[index + 1].name if index + 1 < len(self.agents) else None
            graph.add_conditional_edges(
                agent.name,
                self._route(next_agent),
                self._route_map(next_agent),
            )

        compiled = graph.compile()
        return compiled.invoke(
            {
                "state": state,
                "runtime": runtime,
                "event_bus": event_bus,
                "session_started": session_started,
                "previous_elapsed": previous_elapsed,
                "stop_reason": None,
            }
        )

    def _node(self, agent: BaseAgent):
        def execute_agent(graph_state: AgentGraphState) -> AgentGraphState:
            state = graph_state["state"]
            self.runner._check_run_budget(
                state,
                graph_state["session_started"],
                graph_state["previous_elapsed"],
            )
            if (self.runner.run_dir(state) / "cancel.requested").exists():
                raise RunCancelled("run cancellation requested")

            record = state.stages[agent.name]
            if record.status != StageStatus.COMPLETED:
                self.runner._ensure_dependencies(state, agent)
                self.runner._execute_agent(
                    agent,
                    state,
                    graph_state["runtime"],
                    graph_state["event_bus"],
                )

            stop_reason = self.runner._handle_post_agent_route(
                agent,
                state,
                graph_state["event_bus"],
                graph_state["session_started"],
                graph_state["previous_elapsed"],
            )
            return {"state": state, "stop_reason": stop_reason}

        return execute_agent

    @staticmethod
    def _route(next_agent: str | None):
        def route(graph_state: AgentGraphState) -> str:
            if graph_state.get("stop_reason"):
                return "end"
            return next_agent or "end"

        return route

    @staticmethod
    def _route_map(next_agent: str | None) -> dict[str, str]:
        mapping = {"end": END}
        if next_agent:
            mapping[next_agent] = next_agent
        return mapping
