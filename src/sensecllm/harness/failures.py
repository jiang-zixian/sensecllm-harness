from __future__ import annotations

from enum import Enum

from .errors import RunBudgetExceeded, RunCancelled


class FailureClass(str, Enum):
    CANCELLED = "cancelled"
    BUDGET = "budget"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


_TRANSIENT_MARKERS = (
    "http 408",
    "http 409",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "connection reset",
    "connection aborted",
    "network request",
    "temporarily unavailable",
    "rate limit",
    "timed out",
)


def classify_failure(error: BaseException) -> FailureClass:
    if isinstance(error, RunCancelled):
        return FailureClass.CANCELLED
    if isinstance(error, RunBudgetExceeded):
        return FailureClass.BUDGET
    if isinstance(error, TimeoutError):
        return FailureClass.TIMEOUT
    message = str(error).casefold()
    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return FailureClass.TRANSIENT
    return FailureClass.PERMANENT
