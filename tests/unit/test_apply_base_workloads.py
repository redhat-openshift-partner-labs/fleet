from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_base_workloads import main


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "yaml-output", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.apply_base_workloads.run_with_retry")
def test_apply_success(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List\nitems: []"),
        _ok(stdout="configured"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/base",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        main()
    assert mock_retry.call_count == 2
    kustomize_call = mock_retry.call_args_list[0]
    assert "kustomize" in " ".join(kustomize_call.args[0])
    apply_call = mock_retry.call_args_list[1]
    assert "--kubeconfig=/workspace/kubeconfig" in apply_call.args[0]


@mock.patch("fleet.tasks.apply_base_workloads.run_with_retry")
def test_kustomize_build_fails(mock_retry):
    mock_retry.return_value = _fail(stderr="error building kustomization")
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/base",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_base_workloads.run_with_retry")
def test_apply_fails(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: List"),
        _fail(stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/workspace/source/workloads/base",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_base_workloads.run_with_retry")
def test_uses_source_dir_for_kustomize(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout=""),
        _ok(stdout=""),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            "/custom/workloads/path",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
        ],
    ):
        main()
    kustomize_call = mock_retry.call_args_list[0]
    assert "/custom/workloads/path" in kustomize_call.args[0]
