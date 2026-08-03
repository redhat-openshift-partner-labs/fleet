from unittest import mock

import subprocess

import pytest

from fleet.tasks.finalize_spoke import main


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _argv(*extra):
    return [
        "prog",
        "--cluster-name",
        "test-cluster",
        "--spoke-kubeconfig",
        "/workspace/kubeconfig",
        *extra,
    ]


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_finalize_success(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", _argv()):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_kubeconfig_passed_to_all_calls(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", _argv()):
        main()
    for call in mock_run.call_args_list:
        cmd = call.args[0]
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_installer_pods_deleted_with_label_and_field_selector(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", _argv()):
        main()
    pod_cmd = mock_run.call_args_list[0].args[0]
    assert "pods" in pod_cmd
    assert "-l" in pod_cmd
    assert "app=installer" in pod_cmd
    assert "--field-selector=status.phase=Failed" in pod_cmd
    assert "-A" in pod_cmd
    assert "--ignore-not-found=true" in pod_cmd


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_installer_pod_delete_failure_is_nonfatal(mock_run):
    mock_run.side_effect = [_fail(), _ok()]
    with mock.patch("sys.argv", _argv()):
        main()


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_kubeadmin_secret_deleted(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", _argv()):
        main()
    secret_cmd = mock_run.call_args_list[1].args[0]
    assert "secret" in secret_cmd
    assert "kubeadmin" in secret_cmd
    assert "-n" in secret_cmd
    assert "kube-system" in secret_cmd
    assert "--ignore-not-found=true" in secret_cmd


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_kubeadmin_secret_delete_failure_is_nonfatal(mock_run):
    mock_run.side_effect = [_ok(), _fail()]
    with mock.patch("sys.argv", _argv()):
        main()


@mock.patch("fleet.tasks.finalize_spoke.subprocess.run")
def test_both_operations_fail_still_exits_zero(mock_run):
    mock_run.return_value = _fail()
    with mock.patch("sys.argv", _argv()):
        main()
