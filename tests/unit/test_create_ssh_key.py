from unittest import mock

import subprocess

import pytest

from fleet.tasks.create_ssh_key import main


def _ok(args=None, stdout="", **kwargs):
    return subprocess.CompletedProcess(
        args or [], returncode=0, stdout=stdout, stderr=""
    )


def _fail(args=None, stderr="error", **kwargs):
    return subprocess.CompletedProcess(
        args or [], returncode=1, stdout="", stderr=stderr
    )


@mock.patch("fleet.tasks.create_ssh_key.subprocess.run")
def test_secret_already_exists(mock_run):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        ["oc", "get", "secret", "test-cluster-ssh-key", "-n", "test-cluster"],
        capture_output=True,
        text=True,
    )


@mock.patch("builtins.open", mock.mock_open(read_data="PRIVATE-KEY-DATA"))
@mock.patch("fleet.tasks.create_ssh_key.tempfile.TemporaryDirectory")
@mock.patch("fleet.tasks.create_ssh_key.subprocess.run")
def test_ssh_key_created(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = mock.Mock(return_value="/tmp/fakedir")
    mock_tmpdir.return_value.__exit__ = mock.Mock(return_value=False)
    mock_run.side_effect = [
        _fail(stderr="not found"),
        _ok(),
        _ok(stdout="yaml-output"),
        _ok(),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()

    calls = mock_run.call_args_list
    assert calls[0] == mock.call(
        ["oc", "get", "secret", "test-cluster-ssh-key", "-n", "test-cluster"],
        capture_output=True,
        text=True,
    )
    assert calls[1] == mock.call(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            "/tmp/fakedir/key",
            "-N",
            "",
            "-q",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[2] == mock.call(
        [
            "oc",
            "create",
            "secret",
            "generic",
            "test-cluster-ssh-key",
            "-n",
            "test-cluster",
            "--from-literal=ssh-privatekey=PRIVATE-KEY-DATA",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[3] == mock.call(
        ["oc", "apply", "-f", "-"],
        input="yaml-output",
        capture_output=True,
        text=True,
        check=True,
    )


@mock.patch("fleet.tasks.create_ssh_key.tempfile.TemporaryDirectory")
@mock.patch("fleet.tasks.create_ssh_key.subprocess.run")
def test_keygen_fails(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = mock.Mock(return_value="/tmp/fakedir")
    mock_tmpdir.return_value.__exit__ = mock.Mock(return_value=False)
    mock_run.side_effect = [
        _fail(stderr="not found"),
        subprocess.CalledProcessError(1, "ssh-keygen", stderr="keygen failed"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("builtins.open", mock.mock_open(read_data="PRIVATE-KEY-DATA"))
@mock.patch("fleet.tasks.create_ssh_key.tempfile.TemporaryDirectory")
@mock.patch("fleet.tasks.create_ssh_key.subprocess.run")
def test_apply_fails(mock_run, mock_tmpdir):
    mock_tmpdir.return_value.__enter__ = mock.Mock(return_value="/tmp/fakedir")
    mock_tmpdir.return_value.__exit__ = mock.Mock(return_value=False)
    mock_run.side_effect = [
        _fail(stderr="not found"),
        _ok(),
        _ok(stdout="yaml-output"),
        subprocess.CalledProcessError(1, "oc", stderr="apply failed"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
