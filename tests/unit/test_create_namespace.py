from unittest import mock

import subprocess

import pytest

from fleet.tasks.create_namespace import main


def test_configmap_missing():
    with mock.patch("sys.argv", ["prog", "--cluster-name", "c"]):
        with pytest.raises(SystemExit, match="1"):
            main()


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=1, stdout="", stderr="not found"
    )


@mock.patch("fleet.tasks.create_namespace.subprocess.run")
def test_namespace_already_exists(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.return_value = _run(["oc", "get", "namespace", "test-cluster"])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_called_once_with(
        ["oc", "get", "namespace", "test-cluster"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.create_namespace.subprocess.run")
def test_namespace_created(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _run_fail(["oc", "get", "namespace", "test-cluster"]),
        _run(["oc", "create", "namespace", "test-cluster"]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["oc", "create", "namespace", "test-cluster"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.create_namespace.subprocess.run")
def test_namespace_create_fails(mock_run, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [
        _run_fail(["oc", "get"]),
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    ]
    import pytest

    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()
