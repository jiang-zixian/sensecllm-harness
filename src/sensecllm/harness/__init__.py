from typing import TYPE_CHECKING, Any

from .state import RunState, RunStatus, StageStatus

if TYPE_CHECKING:
    from .runner import HarnessRunner


def __getattr__(name: str) -> Any:
    if name == "HarnessRunner":
        from .runner import HarnessRunner

        return HarnessRunner
    raise AttributeError(name)

__all__ = ["HarnessRunner", "RunState", "RunStatus", "StageStatus"]
