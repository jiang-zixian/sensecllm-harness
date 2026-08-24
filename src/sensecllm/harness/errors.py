class RunCancelled(RuntimeError):
    """Raised when a persisted cancellation request stops a run."""


class RunBudgetExceeded(RuntimeError):
    """Raised when a run exceeds its configured time or attempt budget."""
