from unittest import mock

import subprocess

import pytest

from fleet.tasks.trigger_post_provision import main


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout="pipelinerun.tekton.dev/post-provision-test-cluster created",
        stderr="",
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    ):
        main()
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    cmd = call_args.args[0]
    assert cmd[0] == "oc"
    assert "create" in cmd or "apply" in cmd


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_includes_cluster_and_tier(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "my-cluster", "--tier", "virt"],
    ):
        main()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "my-cluster" in stdin_yaml
    assert "virt" in stdin_yaml
    assert "post-provision" in stdin_yaml


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "base"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.trigger_post_provision.subprocess.run")
def test_trigger_creates_pipelinerun(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="created", stderr=""
    )
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--tier", "ai"],
    ):
        main()
    call_args = mock_run.call_args
    stdin_yaml = call_args.kwargs.get("input", "")
    assert "PipelineRun" in stdin_yaml
    assert "pipelineRef" in stdin_yaml
