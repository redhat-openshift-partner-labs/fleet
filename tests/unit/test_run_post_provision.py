"""Tests for fleet-run-post-provision CLI tool."""

from unittest import mock

import json
import subprocess

import pytest
import yaml

from fleet.tasks.run_post_provision import main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-vc",
    "--tier",
    "base",
    "--namespace",
    "test-ns",
]


def _create_result(name="post-provision-test-vc-abc12"):
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=f"pipelinerun.tekton.dev/{name} created", stderr=""
    )


def _create_fail():
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden")


def _status_result(status, reason):
    cond = json.dumps({"type": "Succeeded", "status": status, "reason": reason})
    return subprocess.CompletedProcess([], returncode=0, stdout=cond, stderr="")


def _status_running():
    return _status_result("Unknown", "Running")


def _status_succeeded():
    return _status_result("True", "Succeeded")


def _status_failed():
    return _status_result("False", "Failed")


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_run_success(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_succeeded()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_run_succeeds_with_completed_reason(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_result("True", "Completed")]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_run_polls_until_success(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _create_result(),
        _status_running(),
        _status_running(),
        _status_succeeded(),
    ]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_create_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_fail()]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 1


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_pipeline_fails(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_failed()]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.run_post_provision.time.time")
@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_timeout(mock_run, _mock_sleep, mock_time, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_time.side_effect = [0.0, 601.0]
    mock_run.side_effect = [_create_result(), _status_running()]
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_pipelinerun_yaml_params(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_succeeded()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    create_call = mock_run.call_args_list[0]
    doc = yaml.safe_load(create_call.kwargs["input"])
    assert doc["kind"] == "PipelineRun"
    assert doc["spec"]["pipelineRef"]["name"] == "post-provision"
    params = {p["name"]: p["value"] for p in doc["spec"]["params"]}
    assert params["cluster-name"] == "test-vc"
    assert params["tier"] == "base"
    assert params["openshift-cluster"] == "false"
    assert params["spoke-kubeconfig"] == "test-vc-admin-kubeconfig"
    expected = {
        "cluster-name",
        "tier",
        "openshift-cluster",
        "spoke-kubeconfig",
        "pipeline-image",
    }
    assert set(params.keys()) == expected


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_pipelinerun_has_workspace_and_sa(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_succeeded()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    create_call = mock_run.call_args_list[0]
    doc = yaml.safe_load(create_call.kwargs["input"])
    trt = doc["spec"]["taskRunTemplate"]
    assert trt["serviceAccountName"] == "fleet-pipeline"
    ws = doc["spec"]["workspaces"][0]
    assert ws["name"] == "shared-workspace"


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_custom_timeout(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_succeeded()]
    argv = BASE_ARGV + ["--timeout", "120"]
    with mock.patch("sys.argv", argv):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_extracts_pipelinerun_name_from_output(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _create_result("post-provision-my-vc-xyz99"),
        _status_succeeded(),
    ]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    poll_call = mock_run.call_args_list[1].args[0]
    assert "post-provision-my-vc-xyz99" in poll_call


@mock.patch("fleet.tasks.run_post_provision.time.sleep")
@mock.patch("fleet.tasks.run_post_provision.subprocess.run")
def test_pipelinerun_includes_envfrom_configmap(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_create_result(), _status_succeeded()]
    with mock.patch("sys.argv", BASE_ARGV):
        main()
    create_call = mock_run.call_args_list[0]
    doc = yaml.safe_load(create_call.kwargs["input"])
    env_from = doc["spec"]["taskRunTemplate"]["podTemplate"]["envFrom"]
    assert env_from == [{"configMapRef": {"name": "fleet-pipeline-defaults"}}]
