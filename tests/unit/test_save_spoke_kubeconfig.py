from unittest import mock

import subprocess

import pytest

from fleet.tasks.save_spoke_kubeconfig import main


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-content-here"))
@mock.patch("fleet.tasks.save_spoke_kubeconfig.subprocess.run")
def test_save_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="secret configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--kubeconfig-file",
            "/workspace/kubeconfig",
        ],
    ):
        main()
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args.args[0]
    assert cmd[0] == "oc"
    assert "apply" in cmd


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.save_spoke_kubeconfig.subprocess.run")
def test_save_creates_secret_with_cluster_name(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "my-cluster",
            "--kubeconfig-file",
            "/workspace/kubeconfig",
        ],
    ):
        main()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "my-cluster-spoke-kubeconfig" in stdin_yaml


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.save_spoke_kubeconfig.subprocess.run")
def test_save_default_namespace(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--kubeconfig-file",
            "/workspace/kubeconfig",
        ],
    ):
        main()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "openshift-pipelines" in stdin_yaml


@mock.patch("builtins.open", side_effect=FileNotFoundError("no such file"))
@mock.patch("fleet.tasks.save_spoke_kubeconfig.subprocess.run")
def test_save_file_not_found(mock_run, mock_open, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--kubeconfig-file",
            "/missing/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.save_spoke_kubeconfig.subprocess.run")
def test_save_apply_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--kubeconfig-file",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
