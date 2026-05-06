from unittest import mock

import subprocess

import pytest

from fleet.tasks.configure_spoke_rbac import main


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_success(mock_run):
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
            "--cluster-admins",
            "",
        ],
    ):
        main()
    assert mock_run.call_count >= 1
    for call in mock_run.call_args_list:
        cmd = call.args[0]
        assert "--kubeconfig=/workspace/kubeconfig" in cmd


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_creates_group_and_binding(mock_run):
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
            "--cluster-admins",
            "",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "cluster-admins" in combined
    assert "ClusterRoleBinding" in combined


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_apply_fails(mock_run):
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
            "--cluster-admins",
            "",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_binds_cluster_admin_role(mock_run):
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
            "--cluster-admins",
            "",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "cluster-admin" in combined


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_empty_cluster_admins_yields_empty_users(mock_run):
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
            "--cluster-admins",
            "",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "users: []" in combined


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_populates_users_from_cluster_admins(mock_run):
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
            "--cluster-admins",
            "alice,bob",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "- alice" in combined
    assert "- bob" in combined
    assert "users: []" not in combined


@mock.patch("fleet.tasks.configure_spoke_rbac.subprocess.run")
def test_rbac_single_cluster_admin(mock_run):
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
            "--cluster-admins",
            "carol",
        ],
    ):
        main()
    all_stdin = [
        c.kwargs.get("input", "")
        for c in mock_run.call_args_list
        if c.kwargs.get("input")
    ]
    combined = "\n".join(all_stdin)
    assert "- carol" in combined
