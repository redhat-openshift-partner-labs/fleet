from unittest import mock

import subprocess

import pytest

from fleet.tasks.seed_test_vcluster import main


def _ok(**kwargs):
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="", **kwargs)


def _fail(**kwargs):
    return subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error", **kwargs
    )


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_seed_success(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _ok()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
        ],
    ):
        main()
    assert mock_run.call_count == 3


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_seed_with_aws_creds(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _ok(), _ok()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
            "--create-aws-creds",
        ],
    ):
        main()
    assert mock_run.call_count == 4
    aws_call = mock_run.call_args_list[3]
    assert "aws-credentials" in aws_call.kwargs.get("input", "")


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_namespace_create_fails(mock_run):
    mock_run.side_effect = [_fail()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 1


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_kubeconfig_secret_fails(mock_run):
    mock_run.side_effect = [_ok(), _fail()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_managedcluster_create_fails(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _fail()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_kubeconfig_file_not_found(mock_run):
    mock_run.side_effect = [_ok()]
    with mock.patch(
        "builtins.open", mock.Mock(side_effect=FileNotFoundError("not found"))
    ):
        with mock.patch(
            "sys.argv",
            [
                "prog",
                "--cluster-name",
                "test-vc",
                "--kubeconfig-file",
                "/tmp/kc",
                "--tier",
                "base",
            ],
        ):
            with pytest.raises(SystemExit, match="1"):
                main()
    assert mock_run.call_count == 1


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_aws_creds_create_fails(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _ok(), _fail()]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-vc",
            "--kubeconfig-file",
            "/tmp/kc",
            "--tier",
            "base",
            "--create-aws-creds",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 4
