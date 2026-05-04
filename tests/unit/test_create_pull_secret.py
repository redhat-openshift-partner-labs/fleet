from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks.create_pull_secret import main

SOURCE_SECRET_JSON = json.dumps(
    {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "pull-secret",
            "namespace": "openshift-config",
            "resourceVersion": "12345",
            "uid": "abc-123",
            "creationTimestamp": "2025-01-01T00:00:00Z",
        },
        "type": "kubernetes.io/dockerconfigjson",
        "data": {
            ".dockerconfigjson": "eyJhdXRocyI6IHt9fQ==",
        },
    }
)


def _ok(stdout=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


def _fail(stderr="error"):
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=stderr)


@mock.patch("fleet.tasks.create_pull_secret.subprocess.run")
def test_secret_already_exists(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        ["oc", "get", "secret", "pull-secret", "-n", "test-cluster"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.create_pull_secret.subprocess.run")
def test_pull_secret_copied(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _fail(stderr="not found"),
        _ok(stdout=SOURCE_SECRET_JSON),
        _ok(),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()

    calls = mock_run.call_args_list
    assert calls[0] == mock.call(
        ["oc", "get", "secret", "pull-secret", "-n", "test-cluster"],
        capture_output=True,
        text=True,
    )
    assert calls[1] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "pull-secret",
            "-n",
            "openshift-config",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    applied_json = json.loads(calls[2].kwargs["input"])
    assert applied_json["metadata"]["namespace"] == "test-cluster"
    assert applied_json["metadata"]["name"] == "pull-secret"
    assert "resourceVersion" not in applied_json["metadata"]
    assert "uid" not in applied_json["metadata"]
    assert "creationTimestamp" not in applied_json["metadata"]
    assert applied_json["type"] == "kubernetes.io/dockerconfigjson"
    assert applied_json["data"][".dockerconfigjson"] == "eyJhdXRocyI6IHt9fQ=="


@mock.patch("fleet.tasks.create_pull_secret.subprocess.run")
def test_source_secret_not_found(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _fail(stderr="not found"),
        subprocess.CalledProcessError(1, "oc", stderr="not found"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_pull_secret.subprocess.run")
def test_apply_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _fail(stderr="not found"),
        _ok(stdout=SOURCE_SECRET_JSON),
        subprocess.CalledProcessError(1, "oc", stderr="apply failed"),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_pull_secret.subprocess.run")
def test_custom_source_params(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _fail(stderr="not found"),
        _ok(stdout=SOURCE_SECRET_JSON),
        _ok(),
    ]
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-namespace",
            "my-ns",
            "--source-secret-name",
            "my-pull-secret",
        ],
    ):
        main()

    calls = mock_run.call_args_list
    assert calls[1] == mock.call(
        [
            "oc",
            "get",
            "secret",
            "my-pull-secret",
            "-n",
            "my-ns",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
