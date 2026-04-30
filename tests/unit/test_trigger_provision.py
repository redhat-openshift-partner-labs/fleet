from unittest import mock

import subprocess

import pytest
import yaml

from fleet.tasks.trigger_provision import main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
]


def _create_result(ok=True):
    if ok:
        return subprocess.CompletedProcess(
            [], returncode=0, stdout="created", stderr=""
        )
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden")


def _run_and_capture_yaml(mock_run, argv):
    mock_run.return_value = _create_result()
    with mock.patch("sys.argv", argv):
        main()
    return yaml.safe_load(mock_run.call_args.kwargs["input"])


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_success(mock_run):
    mock_run.return_value = _create_result()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_includes_cluster_name(mock_run):
    mock_run.return_value = _create_result()
    argv = ["prog", "--cluster-name", "my-cluster"]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    assert "my-cluster" in stdin_yaml


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_references_provision_pipeline(mock_run):
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    assert doc["kind"] == "PipelineRun"
    assert doc["spec"]["pipelineRef"]["name"] == "provision"


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_create_fails(mock_run):
    mock_run.return_value = _create_result(ok=False)
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_workspaces(mock_run):
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    ws = doc["spec"]["workspaces"][0]
    assert ws["name"] == "shared-workspace"
    vct = ws["volumeClaimTemplate"]["spec"]
    assert vct["storageClassName"] == "gp3-csi"
    assert vct["resources"]["requests"]["storage"] == "1Gi"


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_taskruntemplate(mock_run):
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    assert trt["podTemplate"]["securityContext"]["fsGroup"] == 0
