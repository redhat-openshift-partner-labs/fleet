from unittest import mock

import subprocess

import pytest

from fleet.tasks.wait_for_aws_creds import main


@mock.patch("fleet.tasks.wait_for_aws_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_creds.subprocess.run")
def test_secret_found_immediately(mock_run, mock_sleep):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="found", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_sleep.assert_not_called()


@mock.patch("fleet.tasks.wait_for_aws_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_creds.subprocess.run")
def test_secret_found_after_retry(mock_run, mock_sleep):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found"),
        subprocess.CompletedProcess([], returncode=0, stdout="found", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--timeout-seconds", "30"],
    ):
        main()
    mock_sleep.assert_called_once_with(10)


@mock.patch("fleet.tasks.wait_for_aws_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_creds.subprocess.run")
def test_timeout(mock_run, mock_sleep):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--timeout-seconds", "10"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_sleep.call_count == 1
