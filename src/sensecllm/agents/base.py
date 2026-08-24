from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sensecllm.harness.state import RunState


@dataclass
class AgentContext:
    state: RunState
    runtime: Any
    memory: Any = None
    settings: Any = None


class BaseAgent(ABC):
    name: str
    depends_on: tuple[str, ...] = ()

    @abstractmethod
    def execute(self, context: AgentContext) -> Any:
        """Execute one typed domain responsibility."""
