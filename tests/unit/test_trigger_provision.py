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
        import os

        old_value = os.environ.get("FLEET_CONFIGMAP_LOADED")
        os.environ["FLEET_CONFIGMAP_LOADED"] = "true"
        try:
            main()
        finally:
            if old_value is None:
                os.environ.pop("FLEET_CONFIGMAP_LOADED", None)
            else:
                os.environ["FLEET_CONFIGMAP_LOADED"] = old_value
    return yaml.safe_load(mock_run.call_args.kwargs["input"])


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = _create_result()
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_includes_cluster_name(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = _create_result()
    argv = ["prog", "--cluster-name", "my-cluster"]
    with mock.patch("sys.argv", argv):
        main()
    stdin_yaml = mock_run.call_args.kwargs["input"]
    assert "my-cluster" in stdin_yaml


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_references_provision_pipeline(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    assert doc["kind"] == "PipelineRun"
    assert doc["spec"]["pipelineRef"]["name"] == "provision"


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_create_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = _create_result(ok=False)
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_workspaces(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    ws = doc["spec"]["workspaces"][0]
    assert ws["name"] == "shared-workspace"
    vct = ws["volumeClaimTemplate"]["spec"]
    assert vct["storageClassName"] == "gp3-csi"
    assert vct["resources"]["requests"]["storage"] == "1Gi"


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_creates_pipelinerun_with_taskruntemplate(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    assert trt["podTemplate"]["securityContext"]["fsGroup"] == 0


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_only_passes_cluster_name_param(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params == {"cluster-name": "test-cluster"}


@mock.patch("fleet.tasks.trigger_provision.subprocess.run")
def test_trigger_includes_envfrom_configmap(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    doc = _run_and_capture_yaml(mock_run, BASE_ARGV)
    env_from = doc["spec"]["taskRunTemplate"]["podTemplate"]["envFrom"]
    assert env_from == [{"configMapRef": {"name": "fleet-pipeline-defaults"}}]
