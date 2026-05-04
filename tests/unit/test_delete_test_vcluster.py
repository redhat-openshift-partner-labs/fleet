from unittest import mock

import subprocess

import pytest

from fleet.tasks.delete_test_vcluster import main


def _ok(**kwargs):
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="", **kwargs)


def _fail(**kwargs):
    return subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="error", **kwargs
    )


@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_delete_success(mock_run):
    mock_run.side_effect = [_ok(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_vcluster_delete_fails(mock_run):
    mock_run.side_effect = [_ok(), _fail()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 2


@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_managedcluster_delete_tolerant(mock_run):
    mock_run.side_effect = [_fail(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 2
