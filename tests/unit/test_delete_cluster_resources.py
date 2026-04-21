from unittest import mock

import subprocess

import pytest

from fleet.tasks.delete_cluster_resources import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=1, stdout="", stderr="not found"
    )


@mock.patch("fleet.tasks.delete_cluster_resources.subprocess.run")
def test_all_deletions_succeed(mock_run):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 5
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "klusterletaddonconfig",
            "test-cluster",
            "-n",
            "test-cluster",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "managedcluster",
            "test-cluster",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    mock_run.assert_any_call(
        [
            "oc",
            "wait",
            "--for=delete",
            "managedcluster/test-cluster",
            "--timeout=5m",
        ],
        capture_output=True,
        text=True,
    )
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "machinepool",
            "-n",
            "test-cluster",
            "--all",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "clusterdeployment",
            "test-cluster",
            "-n",
            "test-cluster",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.delete_cluster_resources.subprocess.run")
def test_wait_timeout_is_non_fatal(mock_run):
    mock_run.side_effect = [
        _run([]),
        _run([]),
        _run_fail([]),
        _run([]),
        _run([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 5


@mock.patch("fleet.tasks.delete_cluster_resources.subprocess.run")
def test_all_resources_already_deleted(mock_run):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 5
