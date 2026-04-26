from unittest import mock

import subprocess

import pytest
import yaml

from fleet.tasks.trigger_post_provision import main


def _run_and_capture_yaml(mock_run, argv):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch("sys.argv", argv):
        main()
    return yaml.safe_load(mock_run.call_args.kwargs["input"])


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_success(mock_run):
    mock_basedomain = subprocess.CompletedProcess(
        [], returncode=0, stdout="example.com", stderr=""
    )
    mock_create = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    mock_run.side_effect = [mock_basedomain, mock_create]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    ):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_includes_cluster_and_tier(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="example.com", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="created", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "my-cluster", "--tier", "virt"],
    ):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    assert "my-cluster" in stdin_yaml
    assert "virt" in stdin_yaml
    assert "post-provision" in stdin_yaml


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_create_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="example.com", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_basedomain_lookup_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_derives_dns_zones(mock_run):
    doc = _run_and_capture_yaml(
        mock_run,
        ["prog", "--cluster-name", "my-cluster", "--tier", "base"],
    )
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="example.com", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="created", stderr=""),
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "my-cluster", "--tier", "base"],
    ):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    doc = yaml.safe_load(stdin_yaml)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["dns-zones"] == (
        "*.apps.my-cluster.example.com,api.my-cluster.example.com"
    )


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_workspaces(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="example.com", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="created", stderr=""),
    ]
    doc = _run_and_capture_yaml(
        mock_run,
        ["prog", "--cluster-name", "test-cluster", "--tier", "ai"],
    )
    assert doc["kind"] == "PipelineRun"
    assert doc["spec"]["pipelineRef"]["name"] == "post-provision"
    ws = doc["spec"]["workspaces"][0]
    assert ws["name"] == "shared-workspace"
    vct = ws["volumeClaimTemplate"]["spec"]
    assert vct["storageClassName"] == "gp3-csi"
    assert vct["resources"]["requests"]["storage"] == "1Gi"


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_taskruntemplate(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="example.com", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="created", stderr=""),
    ]
    doc = _run_and_capture_yaml(
        mock_run,
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    )
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    assert trt["podTemplate"]["securityContext"]["fsGroup"] == 0
