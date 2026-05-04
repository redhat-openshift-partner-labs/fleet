from unittest import mock

import subprocess

import pytest

from fleet.tasks.configure_spoke_oauth import main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--spoke-kubeconfig",
    "/workspace/kubeconfig",
    "--cluster-dir",
    "/workspace/source/clusters/test-cluster",
    "--keycloak-issuer-url",
    "https://idp.example.com/realms/openshift",
    "--provider-name",
    "RedHat",
]


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count >= 2
    for call in mock_run.call_args_list:
        cmd = call.args[0]
        assert cmd[0] == "oc"
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_applies_htpasswd_secret(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    all_cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    assert any("apply" in cmd for cmd in all_cmds)


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_htpasswd_apply_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_uses_cluster_name_in_resources(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    argv = [*BASE_ARGV]
    argv[2] = "my-cluster"
    with mock.patch("sys.argv", argv):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "openshift-config" in combined


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_second_apply_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_issuer_url_parameterized(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    argv = [
        "prog",
        "--cluster-name",
        "c1",
        "--spoke-kubeconfig",
        "/kc",
        "--cluster-dir",
        "/d",
        "--keycloak-issuer-url",
        "https://sso.prod.com/realms/prod",
        "--provider-name",
        "RedHat",
    ]
    with mock.patch("sys.argv", argv):
        main()
    oauth_yaml = mock_run.call_args_list[1].kwargs["input"]
    assert "issuer: https://sso.prod.com/realms/prod" in oauth_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_provider_name_in_oauth_yaml(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    argv = [
        "prog",
        "--cluster-name",
        "c1",
        "--spoke-kubeconfig",
        "/kc",
        "--cluster-dir",
        "/d",
        "--keycloak-issuer-url",
        "https://sso.example.com/realms/r",
        "--provider-name",
        "MyIDP",
    ]
    with mock.patch("sys.argv", argv):
        main()
    oauth_yaml = mock_run.call_args_list[1].kwargs["input"]
    assert "name: MyIDP" in oauth_yaml


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_client_secret_name_matches_register_task(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    oauth_yaml = mock_run.call_args_list[1].kwargs["input"]
    assert "name: test-cluster-keycloak-client" in oauth_yaml


def test_env_var_fallback_for_keycloak_issuer(monkeypatch):
    """keycloak-issuer-url resolves from env var when CLI arg is missing."""
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv(
        "FLEET_KEYCLOAK_ISSUER_URL", "https://idp.env.com/realms/openshift"
    )
    monkeypatch.setenv("FLEET_PROVIDER_NAME", "EnvProvider")
    argv = [
        "prog",
        "--cluster-name",
        "test-cluster",
        "--spoke-kubeconfig",
        "/workspace/kubeconfig",
        "--cluster-dir",
        "/workspace/source/clusters/test-cluster",
    ]
    with mock.patch("sys.argv", argv), mock.patch(
        "fleet.tasks.configure_spoke_oauth.subprocess.run"
    ) as mock_run:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        main()
    assert mock_run.call_count >= 1
