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
def test_trigger_success(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_includes_cluster_and_tier(mock_run):
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
    ]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    assert "my-cluster" in stdin_yaml
    assert "virt" in stdin_yaml
    assert "post-provision" in stdin_yaml


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_create_fails(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result(ok=False)]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_basedomain_lookup_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_derives_dns_zones(mock_run):
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
def test_trigger_creates_pipelinerun_with_workspaces(mock_run):
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
def test_trigger_creates_pipelinerun_with_taskruntemplate(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    assert trt["podTemplate"]["securityContext"]["fsGroup"] == 0


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_passes_base_domain_and_issuer_url(mock_run):
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
    ]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    doc = yaml.safe_load(stdin_yaml)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["base-domain"] == "labs.example.com"
    assert params["keycloak-issuer-url"] == "https://sso.prod.com/realms/prod"
