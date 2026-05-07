import subprocess
from unittest import mock

import pytest

from fleet._retry import run_with_retry


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "ok", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet._retry.time.sleep")
@mock.patch("fleet._retry.subprocess.run")
def test_succeeds_first_try(mock_run, mock_sleep):
    mock_run.return_value = _ok()
    result = run_with_retry(["echo", "hi"])
    assert result.returncode == 0
    assert mock_run.call_count == 1
    mock_sleep.assert_not_called()


@mock.patch("fleet._retry.time.sleep")
@mock.patch("fleet._retry.subprocess.run")
def test_succeeds_after_transient_failure(mock_run, mock_sleep):
    mock_run.side_effect = [_fail(), _ok()]
    result = run_with_retry(["oc", "apply"], max_attempts=3, backoff=2)
    assert result.returncode == 0
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once_with(2)


@mock.patch("fleet._retry.time.sleep")
@mock.patch("fleet._retry.subprocess.run")
def test_exhausts_retries(mock_run, mock_sleep):
    mock_run.return_value = _fail()
    result = run_with_retry(["oc", "apply"], max_attempts=3, backoff=1)
    assert result.returncode == 1
    assert mock_run.call_count == 3
    assert mock_sleep.call_count == 2


@mock.patch("fleet._retry.time.sleep")
@mock.patch("fleet._retry.subprocess.run")
def test_passes_kwargs_through(mock_run, mock_sleep):
    mock_run.return_value = _ok()
    run_with_retry(
        ["oc", "apply", "-f", "-"],
        input="yaml",
        capture_output=True,
        text=True,
    )
    mock_run.assert_called_once_with(
        ["oc", "apply", "-f", "-"],
        input="yaml",
        capture_output=True,
        text=True,
    )


@mock.patch("fleet._retry.time.sleep")
@mock.patch("fleet._retry.subprocess.run")
def test_single_attempt_no_retry(mock_run, mock_sleep):
    mock_run.return_value = _fail()
    result = run_with_retry(["cmd"], max_attempts=1)
    assert result.returncode == 1
    assert mock_run.call_count == 1
    mock_sleep.assert_not_called()
