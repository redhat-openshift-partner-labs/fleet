from unittest import mock

import subprocess

import pytest

from fleet.tasks.extract_kubeconfig import main


@mock.patch("fleet.tasks.extract_kubeconfig.subprocess.run")
def test_extract_with_secret_ref(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(
            [], returncode=0, stdout="my-kubeconfig-secret", stderr=""
        ),
        subprocess.CompletedProcess([], returncode=0, stdout="kubeconfig", stderr=""),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--output-dir", "/out"]
    ):
        main()
    assert mock_run.call_count == 2
    extract_call = mock_run.call_args_list[1]
    assert "secret/my-kubeconfig-secret" in extract_call.args[0]


@mock.patch("fleet.tasks.extract_kubeconfig.subprocess.run")
def test_extract_fallback_secret_name(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found"),
        subprocess.CompletedProcess([], returncode=0, stdout="kubeconfig", stderr=""),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--output-dir", "/out"]
    ):
        main()
    extract_call = mock_run.call_args_list[1]
    assert "secret/test-cluster-admin-kubeconfig" in extract_call.args[0]


@mock.patch("fleet.tasks.extract_kubeconfig.subprocess.run")
def test_extract_fails(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="secret-name", stderr=""),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="error"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--output-dir", "/out"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
