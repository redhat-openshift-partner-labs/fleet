from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_crossplane_creds import main


@mock.patch("fleet.tasks.apply_crossplane_creds.subprocess.run")
def test_apply_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="apiVersion: v1\nkind: User", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="applied", stderr=""),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        main()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["kustomize", "build", "/src/crossplane"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_crossplane_creds.subprocess.run")
def test_kustomize_build_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error"
    )
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_crossplane_creds.subprocess.run")
def test_oc_apply_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-content", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
