"""Structured logging for fleet pipeline tasks.

Log lines are prefixed with [task-name] for grep-ability in Tekton pipeline logs.
info, error and warn all write to stderr. stdout stays free for a value
that a Tekton Task reads into a result.

Each message includes the seconds of the monotonic clock.

Usage (each task):
    from fleet.tasks._log import configure, error, info, warn
    configure("task-name")           # once in main()
    info("progress message")         # stderr
    error("error message")           # stderr
    warn("warning message")          # stderr
"""

import sys
import time

_TASK: str = "fleet"


def configure(task: str) -> None:  # pylint: disable=global-statement
    """Set the task name prefix. Call once at task start."""
    global _TASK
    _TASK = task


def _prefix() -> str:
    """Build the full timestamped prefix."""
    elapsed = time.monotonic()
    return f"[{_TASK} [{elapsed:6.1f}s]"


def info(message: str) -> None:
    """Log an informational (progress/success) message to stderr."""
    print(f"[info] {_prefix()} {message}", file=sys.stderr)


def error(message: str) -> None:
    """Log an error message to stderr."""
    print(f"[error] {_prefix()} {message}", file=sys.stderr)


def warn(message: str) -> None:
    """Log a warning (non-fatal) message to stderr."""
    print(f"[warn]  {_prefix()} {message}", file=sys.stderr)
