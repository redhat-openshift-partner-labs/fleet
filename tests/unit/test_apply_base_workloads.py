from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_base_workloads import main


@mock.patch("fleet.tasks.apply_base_workloads.subprocess.run")
def test_apply_success(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="apiVersion: v1\nkind: List\nitems: []", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
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
    assert mock_run.call_count == 2
    kustomize_call = mock_run.call_args_list[0]
    assert "kustomize" in " ".join(kustomize_call.args[0])
    apply_call = mock_run.call_args_list[1]
    assert "--kubeconfig=/workspace/kubeconfig" in apply_call.args[0]


@mock.patch("fleet.tasks.apply_base_workloads.subprocess.run")
def test_kustomize_build_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error building kustomization"
    )
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


@mock.patch("fleet.tasks.apply_base_workloads.subprocess.run")
def test_apply_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="apiVersion: v1\nkind: List", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
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


@mock.patch("fleet.tasks.apply_base_workloads.subprocess.run")
def test_uses_source_dir_for_kustomize(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
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
    kustomize_call = mock_run.call_args_list[0]
    assert "/custom/workloads/path" in kustomize_call.args[0]
