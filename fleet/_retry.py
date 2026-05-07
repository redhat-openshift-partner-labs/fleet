"""Retry wrapper for subprocess commands that may hit transient failures."""

import subprocess
import time
from typing import Any

from fleet.tasks._log import info, error


def run_with_retry(
    cmd: list[str],
    max_attempts: int = 3,
    backoff: int = 5,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, max_attempts + 1):
        last_result = subprocess.run(cmd, **kwargs)
        if last_result.returncode == 0:
            return last_result
        if attempt < max_attempts:
            info(
                f"  -> attempt {attempt}/{max_attempts} failed, retrying in {backoff}s..."
            )
            error(f"  -> stderr: {last_result.stderr}")
            time.sleep(backoff)
    return last_result  # type: ignore[return-value]
