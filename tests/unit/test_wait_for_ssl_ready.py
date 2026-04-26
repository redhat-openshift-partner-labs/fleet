from unittest import mock

import subprocess

import pytest

from fleet.tasks.wait_for_ssl_ready import main


@mock.patch("fleet.tasks.wait_for_ssl_ready.subprocess.run")
def test_wait_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "wait",
            "certificate/test-cluster-tls",
            "--for=condition=Ready",
            "--timeout=15m",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.wait_for_ssl_ready.subprocess.run")
def test_wait_custom_timeout(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--timeout", "20m"]
    ):
        main()
    assert "--timeout=20m" in mock_run.call_args.args[0]


@mock.patch("fleet.tasks.wait_for_ssl_ready.subprocess.run")
def test_wait_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="timed out"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
