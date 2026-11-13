from unittest import mock

import subprocess
from pathlib import Path

import pytest
import yaml

from fleet.tasks.trigger_post_provision import PIPELINE_TIMEOUT, main

TRIGGER_TEMPLATE = (
    Path(__file__).parent.parent.parent
    / "tekton"
    / "triggers"
    / "triggertemplate-post-provision.yaml"
)

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--tier",
    "base",
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
def test_trigger_only_passes_per_run_params(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert set(params.keys()) == {
        "cluster-name",
        "tier",
        "dns-zones",
        "htpasswd-provider-name",
        "openshift-ai-version",
        "ai-accelerator",
        "timezone",
        "schedule",
        "podvm-instance-type",
    }


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_forwards_htpasswd_provider_name(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [*BASE_ARGV, "--htpasswd-provider-name", "PartnerIDP"]
    doc = _run_and_capture_yaml(mock_run, argv)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["htpasswd-provider-name"] == "PartnerIDP"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_htpasswd_provider_name_defaults(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["htpasswd-provider-name"] == "htpasswd"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_openshift_ai_version_defaults_to_v3(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["openshift-ai-version"] == "v3"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_forwards_openshift_ai_version(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [*BASE_ARGV, "--openshift-ai-version", "v2"]
    doc = _run_and_capture_yaml(mock_run, argv)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["openshift-ai-version"] == "v2"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_ai_accelerator_defaults_to_nvidia_gpu(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["ai-accelerator"] == "nvidia-gpu"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_forwards_ai_accelerator(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [*BASE_ARGV, "--ai-accelerator", "none"]
    doc = _run_and_capture_yaml(mock_run, argv)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["ai-accelerator"] == "none"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_cronjob_settings_default(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["timezone"] == "America/Chicago"
    assert params["schedule"] == "00 08 * * 1-5"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_forwards_cronjob_settings(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [
        *BASE_ARGV,
        "--timezone",
        "Europe/Berlin",
        "--schedule",
        "30 07 * * 1",
    ]
    doc = _run_and_capture_yaml(mock_run, argv)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["timezone"] == "Europe/Berlin"
    assert params["schedule"] == "30 07 * * 1"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_podvm_instance_type_defaults_to_empty(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    # Quoted in the YAML: an unquoted empty value would be null, not the empty string
    assert params["podvm-instance-type"] == ""


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_forwards_podvm_instance_type(mock_run):
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    argv = [*BASE_ARGV, "--podvm-instance-type", "m6a.large"]
    doc = _run_and_capture_yaml(mock_run, argv)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["podvm-instance-type"] == "m6a.large"
    assert 'value: "m6a.large"' in mock_run.call_args.kwargs["input"]


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_sets_the_pipeline_timeout(mock_run):
    """Build task limit 2h, apply-coco-workloads limit 2h, 1h for the other tasks."""
    mock_run.side_effect = [_basedomain_result(), _create_result()]
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    assert PIPELINE_TIMEOUT == "5h"
    assert doc["spec"]["timeouts"] == {"pipeline": "5h"}


def test_trigger_template_sets_the_same_pipeline_timeout():
    """The EventListener creates the same PipelineRun from the TriggerTemplate."""
    template = yaml.safe_load(TRIGGER_TEMPLATE.read_text())
    (run,) = template["spec"]["resourcetemplates"]
    assert run["spec"]["timeouts"] == {"pipeline": PIPELINE_TIMEOUT}
