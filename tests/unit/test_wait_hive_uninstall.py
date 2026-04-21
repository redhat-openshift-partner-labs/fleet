from unittest import mock

import subprocess

import pytest

from fleet.tasks.wait_hive_uninstall import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=1, stdout="", stderr="not found"
    )


@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_cd_exists_wait_succeeds(mock_run):
    mock_run.side_effect = [_run([]), _run([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        [
            "oc",
            "get",
            "clusterdeployment",
            "test-cluster",
            "-n",
            "test-cluster",
        ],
        capture_output=True,
        text=True,
    )
    mock_run.assert_any_call(
        [
            "oc",
            "wait",
            "--for=delete",
            "clusterdeployment/test-cluster",
            "-n",
            "test-cluster",
            "--timeout=25m",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_cd_already_gone(mock_run):
    mock_run.return_value = _run_fail([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_wait_timeout_exits_1(mock_run):
    mock_run.side_effect = [_run([]), _run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_custom_timeout(mock_run):
    mock_run.side_effect = [_run([]), _run([])]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--timeout", "15m"],
    ):
        main()
    assert "--timeout=15m" in mock_run.call_args_list[1].args[0]


@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_default_timeout(mock_run):
    mock_run.side_effect = [_run([]), _run([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert "--timeout=25m" in mock_run.call_args_list[1].args[0]
