from unittest import mock

import subprocess

import pytest

from fleet.tasks.transform_aws_creds import main


@mock.patch("fleet.tasks.transform_aws_creds.subprocess.run")
def test_transform_success(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="bXl1c2Vy", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="bXlwYXNz", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-output", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="", stderr=""),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()

    calls = mock_run.call_args_list
    assert calls[0] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "aws-credentials-raw",
            "-n",
            "test-cluster",
            "-o",
            "jsonpath={.data.username}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert calls[1] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "aws-credentials-raw",
            "-n",
            "test-cluster",
            "-o",
            "jsonpath={.data.password}",
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
            "aws-credentials",
            "-n",
            "test-cluster",
            "--from-literal=aws_access_key_id=myuser",
            "--from-literal=aws_secret_access_key=mypass",
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


@mock.patch("fleet.tasks.transform_aws_creds.subprocess.run")
def test_extraction_failure(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="not found")
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.transform_aws_creds.subprocess.run")
def test_create_failure(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="bXl1c2Vy", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="bXlwYXNz", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="yaml-output", stderr=""),
        subprocess.CalledProcessError(1, "oc", stderr="apply failed"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
