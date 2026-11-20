from unittest import mock

import subprocess

import pytest

from fleet.tasks.wait_hive_uninstall import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=0, stdout="clusterdeployment.hive.openshift.io/test-cluster\n"
    )


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
            "--ignore-not-found=true",
            "--request-timeout=30s",
            "-o",
            "name",
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
    mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once()


@pytest.mark.parametrize("lookup_fails", [True, False])
@mock.patch("fleet.tasks.wait_hive_uninstall.subprocess.run")
def test_lookup_or_wait_failure_exits_1(mock_run, lookup_fails):
    expected_calls = 1 if lookup_fails else 2
    mock_run.side_effect = [_run([])] * (expected_calls - 1) + [_run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == expected_calls


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
