from unittest import mock

import subprocess

import pytest

from fleet.tasks.label_post_provision import main


@mock.patch("fleet.tasks.label_post_provision.subprocess.run")
def test_label_success(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout="labeled", stderr=""
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "label",
            "managedcluster/test-cluster",
            "provisioned=true",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.label_post_provision.subprocess.run")
def test_label_fails(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
