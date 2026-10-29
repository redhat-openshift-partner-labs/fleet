from unittest import mock

import subprocess

import pytest

from fleet.tasks.verify_deprovision import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=1, stdout="", stderr="not found"
    )


def _out(stdout):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


# Label lookup (nothing extra labelled) + IAM existence check (nothing left)
IAM_GONE = [_run([]), _run([])]
CORE_GONE = [_run_fail([])] * 4


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_all_resources_gone(mock_run):
    mock_run.side_effect = CORE_GONE + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_namespace_still_exists(mock_run):
    mock_run.side_effect = [
        _run([]),
        _run_fail([]),
        _run_fail([]),
        _run_fail([]),
    ] + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_managedcluster_still_exists(mock_run):
    mock_run.side_effect = [
        _run_fail([]),
        _run([]),
        _run_fail([]),
        _run_fail([]),
    ] + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_clusterdeployment_still_exists(mock_run):
    mock_run.side_effect = [
        _run_fail([]),
        _run_fail([]),
        _run([]),
        _run_fail([]),
    ] + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_hub_cronjob_still_exists(mock_run):
    mock_run.side_effect = [
        _run_fail([]),
        _run_fail([]),
        _run_fail([]),
        _run([]),
    ] + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_two_resources_remain(mock_run):
    mock_run.side_effect = [_run([]), _run([]), _run_fail([]), _run_fail([])] + IAM_GONE
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_all_resources_remain(mock_run):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_iam_check_uses_known_and_labelled_names(mock_run):
    mock_run.side_effect = CORE_GONE + [
        _out("user.iam.aws.upbound.io/test-cluster-extra\n"),
        _run([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    check = mock_run.call_args_list[-1].args[0]
    assert check[:2] == ["oc", "get"] and check[-3:] == [
        "--ignore-not-found",
        "-o",
        "name",
    ]
    assert "user.iam/test-cluster-extra" in check
    assert "accesskey.iam/test-cluster-access-key" in check


@mock.patch("fleet.tasks.verify_deprovision.warn")
@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_leftover_iam_fails(mock_run, mock_warn):
    left = "accesskey.iam.aws.upbound.io/test-cluster-ingress-access-key"
    mock_run.side_effect = CORE_GONE + [_run([]), _out(f"{left}\n")]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert left in " ".join(str(c) for c in mock_warn.call_args_list)


@mock.patch("fleet.tasks.verify_deprovision.subprocess.run")
def test_iam_check_failure_fails(mock_run):
    """A failed oc get proves nothing is gone."""
    mock_run.side_effect = CORE_GONE + [_run([]), _run_fail([])]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
