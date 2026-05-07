from unittest import mock

import subprocess

import pytest

from fleet.tasks.validate_inputs import main


def _ok(*_args, **_kwargs):
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")


def _fail(*_args, **_kwargs):
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found")


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_all_secrets_present(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 3


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_missing_secret_fails(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _fail()]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_checks_correct_secrets(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "mycluster"]):
        main()
    secrets_checked = [call.args[0][3] for call in mock_run.call_args_list]
    assert secrets_checked == [
        "aws-credentials",
        "pull-secret",
        "mycluster-ssh-key",
    ]


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_imageset_validated_when_provided(mock_run):
    mock_run.return_value = _ok()
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "c1", "--image-set", "img4.21.13-x86-64-appsub"],
    ):
        main()
    last_call = mock_run.call_args_list[-1]
    assert last_call == mock.call(
        ["oc", "get", "clusterimagesets.hive.openshift.io", "img4.21.13-x86-64-appsub"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_imageset_missing_fails(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _ok(), _fail()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "c1", "--image-set", "nonexistent"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_no_imageset_flag_skips_check(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "c1"]):
        main()
    assert mock_run.call_count == 3
