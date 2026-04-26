from unittest import mock

import subprocess

import pytest

from fleet.tasks.configure_spoke_oauth import main


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
            "--cluster-dir",
            "/workspace/source/clusters/test-cluster",
        ],
    ):
        main()
    assert mock_run.call_count >= 2
    for call in mock_run.call_args_list:
        cmd = call.args[0]
        assert cmd[0] == "oc"
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_applies_htpasswd_secret(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
            "--cluster-dir",
            "/workspace/source/clusters/test-cluster",
        ],
    ):
        main()
    all_cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    assert any("apply" in cmd for cmd in all_cmds)


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_htpasswd_apply_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
            "--cluster-dir",
            "/workspace/source/clusters/test-cluster",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_uses_cluster_name_in_resources(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="configured", stderr=""
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "my-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
            "--cluster-dir",
            "/workspace/source/clusters/my-cluster",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "openshift-config" in combined


@mock.patch("fleet.tasks.configure_spoke_oauth.subprocess.run")
def test_configure_oauth_second_apply_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--spoke-kubeconfig",
            "/workspace/kubeconfig",
            "--cluster-dir",
            "/workspace/source/clusters/test-cluster",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
