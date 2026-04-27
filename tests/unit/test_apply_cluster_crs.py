from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_cluster_crs import main


@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
def test_apply_success(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-output", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="applied", stderr=""),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        main()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["kustomize", "build", "/repo/hive"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
def test_kustomize_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error"
    )
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
def test_oc_apply_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="yaml", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
