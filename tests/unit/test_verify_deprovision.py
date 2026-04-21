from unittest import mock

import subprocess

import pytest

from fleet.tasks.verify_deprovision import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=1, stdout="", stderr="not found"
    )


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_all_resources_gone(mock_run):
    mock_run.return_value = _run_fail([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 3


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_namespace_still_exists(mock_run):
    mock_run.side_effect = [_run([]), _run_fail([]), _run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_managedcluster_still_exists(mock_run):
    mock_run.side_effect = [_run_fail([]), _run([]), _run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_clusterdeployment_still_exists(mock_run):
    mock_run.side_effect = [_run_fail([]), _run_fail([]), _run([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_two_resources_remain(mock_run):
    mock_run.side_effect = [_run([]), _run([]), _run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_all_resources_remain(mock_run):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
