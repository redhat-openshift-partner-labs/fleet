from unittest import mock

import subprocess

import pytest

import yaml

from fleet.tasks._test_vcluster import ABSENT, FOREIGN, OWNED, OWNER_LABEL
from fleet.tasks.seed_test_vcluster import main

SEED_ARGV = [
    "prog",
    "--cluster-name",
    "test-vc",
    "--kubeconfig-file",
    "/tmp/kc",
    "--tier",
    "base",
]


@pytest.fixture(autouse=True)
def guard():
    """The name is of a test and its namespace does not exist; a test changes the mocks."""
    module = "fleet.tasks.seed_test_vcluster"
    with (
        mock.patch(f"{module}.refusal", return_value=None) as refusal,
        mock.patch(f"{module}.namespace_state", return_value=ABSENT) as state,
        mock.patch(f"{module}.has_vcluster", return_value=False) as vcluster,
    ):
        yield mock.Mock(refusal=refusal, namespace_state=state, has_vcluster=vcluster)


def _ok(**kwargs):
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="", **kwargs)


def _fail(**kwargs):
    return subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error", **kwargs
    )


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_seed_success(mock_run):
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
        ],
    ):
        main()
    assert mock_run.call_count == 4


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_seed_with_aws_creds(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _ok(), _ok(), _ok()]
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
    assert mock_run.call_count == 5
    aws_call = mock_run.call_args_list[4]
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
    mock_run.side_effect = [_ok(), _ok(), _ok(), _ok(), _fail()]
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
    assert mock_run.call_count == 5


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_auto_import_secret_created(mock_run):
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
        ],
    ):
        main()
    import_call = mock_run.call_args_list[3]
    assert "auto-import-secret" in import_call.kwargs.get("input", "")
    assert "kubeconfig-data" in import_call.kwargs.get("input", "")


@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_auto_import_secret_fails(mock_run):
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
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_refuses_the_name_of_a_real_cluster(mock_run, guard):
    guard.refusal.return_value = "ClusterDeployment test-vc exists in namespace test-vc"
    with mock.patch("sys.argv", SEED_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    guard.refusal.assert_called_once_with("test-vc")
    mock_run.assert_not_called()


@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_refuses_a_namespace_that_no_test_created(mock_run, guard):
    guard.namespace_state.return_value = FOREIGN
    with mock.patch("sys.argv", SEED_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    guard.has_vcluster.assert_called_once_with("test-vc", "test-vc")
    mock_run.assert_not_called()


@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_refuses_when_the_namespace_cannot_be_read(mock_run, guard):
    guard.namespace_state.side_effect = RuntimeError("cannot read namespace test-vc")
    with mock.patch("sys.argv", SEED_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_not_called()


@pytest.mark.parametrize(
    ("state", "vcluster"), [(ABSENT, False), (OWNED, False), (FOREIGN, True)]
)
@mock.patch("builtins.open", mock.mock_open(read_data="kubeconfig-data"))
@mock.patch("fleet.tasks.seed_test_vcluster.subprocess.run")
def test_namespace_carries_the_label_of_the_test(mock_run, guard, state, vcluster):
    # FOREIGN with a vCluster: the namespace is the one vcluster create made.
    guard.namespace_state.return_value = state
    guard.has_vcluster.return_value = vcluster
    mock_run.side_effect = [_ok(), _ok(), _ok(), _ok()]
    with mock.patch("sys.argv", SEED_ARGV):
        main()
    namespace = yaml.safe_load(mock_run.call_args_list[0].kwargs["input"])
    assert namespace["kind"] == "Namespace"
    assert namespace["metadata"] == {
        "name": "test-vc",
        "labels": {OWNER_LABEL: "test-vc"},
    }
