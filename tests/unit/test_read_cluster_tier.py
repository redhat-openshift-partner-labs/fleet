from unittest import mock

import subprocess

import pytest

from fleet.tasks.read_cluster_tier import main


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_success(mock_run, capsys, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="base", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "get",
            "managedcluster",
            "test-cluster",
            "-o",
            "jsonpath={.metadata.labels.tier}",
        ],
        capture_output=True,
        text=True,
    )
    captured = capsys.readouterr()
    assert captured.out.strip() == "base"
    assert "[info]" in captured.err
    assert "[read-cluster-tier" in captured.err
    assert "tier value:" in captured.err


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.read_cluster_tier.subprocess.run")
def test_read_tier_empty(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
