from unittest import mock

import subprocess

import pytest

from fleet.tasks.extract_cert_material import main


@mock.patch("fleet.tasks.extract_cert_material.subprocess.run")
def test_extract_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout="secret/test-cluster-leaf-cert configured",
            stderr="",
        ),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 2
    get_call = mock_run.call_args_list[0]
    assert "secret/test-cluster-wildcard-certificate" in " ".join(get_call.args[0])
    apply_call = mock_run.call_args_list[1]
    cmd = apply_call.args[0]
    assert cmd[0] == "oc"
    assert "apply" in cmd


@mock.patch("fleet.tasks.extract_cert_material.subprocess.run")
def test_extract_creates_leaf_cert_secret(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "my-cluster", "--namespace", "custom-ns"]
    ):
        main()
    apply_call = mock_run.call_args_list[1]
    stdin_yaml = apply_call.kwargs.get("input", "")
    assert "my-cluster-leaf-cert" in stdin_yaml


@mock.patch("fleet.tasks.extract_cert_material.subprocess.run")
def test_extract_default_namespace(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    get_call = mock_run.call_args_list[0]
    cmd = " ".join(get_call.args[0])
    assert "openshift-ingress" in cmd


@mock.patch("fleet.tasks.extract_cert_material.subprocess.run")
def test_get_secret_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.extract_cert_material.subprocess.run")
def test_apply_leaf_cert_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [],
            returncode=0,
            stdout='{"tls.crt":"Y2VydA==","tls.key":"a2V5"}',
            stderr="",
        ),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
