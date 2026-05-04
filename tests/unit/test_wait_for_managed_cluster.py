from unittest import mock

import subprocess

import pytest

from fleet.tasks.wait_for_managed_cluster import main


@mock.patch("fleet.tasks.wait_for_managed_cluster.subprocess.run")
def test_wait_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "wait",
            "--for=condition=ManagedClusterJoined",
            "managedcluster/test-cluster",
            "--timeout=15m",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.wait_for_managed_cluster.subprocess.run")
def test_wait_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="timed out"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
