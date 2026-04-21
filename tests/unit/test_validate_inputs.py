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
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.validate_inputs.subprocess.run")
def test_missing_secret_fails(mock_run):
    mock_run.side_effect = [_ok(), _ok(), _fail(), _ok()]
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
        "mycluster-install-config",
    ]
