from unittest import mock

import subprocess

import pytest
import yaml

from fleet.tasks.trigger_post_provision import main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--tier",
    "base",
    "--base-domain",
    "example.com",
    "--keycloak-issuer-url",
    "https://keycloak.example.com/realms/openshift",
    "--keycloak-url",
    "https://keycloak.example.com",
    "--keycloak-realm",
    "openshift",
    "--keycloak-admin-secret",
    "keycloak-admin",
    "--auth-realm",
    "master",
    "--acme-email",
    "certs@example.com",
]


def _basedomain_result(domain="example.com"):
    return subprocess.CompletedProcess([], returncode=0, stdout=domain, stderr="")


def _create_result(ok=True):
    if ok:
        return subprocess.CompletedProcess(
            [], returncode=0, stdout="created", stderr=""
        )
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden")


def _run_and_capture_yaml(mock_run, argv):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch("sys.argv", argv):
        main()
    return yaml.safe_load(mock_run.call_args.kwargs["input"])


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_includes_cluster_and_tier(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [
        "prog",
        "--cluster-name",
        "my-cluster",
        "--tier",
        "virt",
        "--base-domain",
        "example.com",
        "--keycloak-issuer-url",
        "https://kc.example.com/realms/r",
        "--keycloak-url",
        "https://kc.example.com",
        "--keycloak-realm",
        "r",
        "--keycloak-admin-secret",
        "keycloak-admin",
        "--auth-realm",
        "master",
        "--acme-email",
        "certs@example.com",
    ]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    assert "my-cluster" in stdin_yaml
    assert "virt" in stdin_yaml
    assert "post-provision" in stdin_yaml


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_create_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result(ok=False)]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_basedomain_lookup_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_derives_dns_zones(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [
        "prog",
        "--cluster-name",
        "my-cluster",
        "--tier",
        "base",
        "--base-domain",
        "example.com",
        "--keycloak-issuer-url",
        "https://kc.example.com/realms/r",
        "--keycloak-url",
        "https://kc.example.com",
        "--keycloak-realm",
        "r",
        "--keycloak-admin-secret",
        "keycloak-admin",
        "--auth-realm",
        "master",
        "--acme-email",
        "certs@example.com",
    ]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    doc = yaml.safe_load(stdin_yaml)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["dns-zones"] == (
        "*.apps.my-cluster.example.com,api.my-cluster.example.com"
    )


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_workspaces(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    assert doc["kind"] == "PipelineRun"
    assert doc["spec"]["pipelineRef"]["name"] == "post-provision"
    ws = doc["spec"]["workspaces"][0]
    assert ws["name"] == "shared-workspace"
    vct = ws["volumeClaimTemplate"]["spec"]
    assert vct["storageClassName"] == "gp3-csi"
    assert vct["resources"]["requests"]["storage"] == "1Gi"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_taskruntemplate(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    assert trt["podTemplate"]["securityContext"]["fsGroup"] == 0


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_passes_keycloak_and_auth_params(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = BASE_ARGV[:]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    doc = yaml.safe_load(stdin_yaml)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["keycloak-url"] == "https://keycloak.example.com"
    assert params["keycloak-realm"] == "openshift"
    assert params["keycloak-admin-secret"] == "keycloak-admin"
    assert params["auth-realm"] == "master"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_passes_base_domain_and_issuer_url(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [
        "prog",
        "--cluster-name",
        "c1",
        "--tier",
        "ai",
        "--base-domain",
        "labs.example.com",
        "--keycloak-issuer-url",
        "https://sso.prod.com/realms/prod",
        "--keycloak-url",
        "https://sso.prod.com",
        "--keycloak-realm",
        "prod",
        "--keycloak-admin-secret",
        "keycloak-admin",
        "--auth-realm",
        "master",
        "--acme-email",
        "certs@prod.com",
    ]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    doc = yaml.safe_load(stdin_yaml)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["base-domain"] == "labs.example.com"
    assert params["keycloak-issuer-url"] == "https://sso.prod.com/realms/prod"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_passes_acme_email(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["acme-email"] == "certs@example.com"


def test_env_var_fallback(monkeypatch):
    """Params resolve from env vars when CLI args are missing."""
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    monkeypatch.setenv("FLEET_BASE_DOMAIN", "env.example.com")
    monkeypatch.setenv(
        "FLEET_KEYCLOAK_ISSUER_URL", "https://kc.env.com/realms/openshift"
    )
    monkeypatch.setenv("FLEET_KEYCLOAK_URL", "https://kc.env.com")
    monkeypatch.setenv("FLEET_KEYCLOAK_REALM", "env-realm")
    monkeypatch.setenv("FLEET_KEYCLOAK_ADMIN_SECRET", "env-secret")
    monkeypatch.setenv("FLEET_AUTH_REALM", "env-auth")
    monkeypatch.setenv("FLEET_ACME_EMAIL", "env@example.com")
    argv = ["prog", "--cluster-name", "test-cluster", "--tier", "base"]
    with mock.patch("sys.argv", argv), mock.patch(
        "fleet.tasks.trigger_post_provision.subprocess.run"
    ) as mock_run:
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, stdout="example.com", stderr=""),
            subprocess.CompletedProcess(
                [], 0, stdout="pipelinerun/pr created", stderr=""
            ),
        ]
        main()
    assert mock_run.call_count == 2
