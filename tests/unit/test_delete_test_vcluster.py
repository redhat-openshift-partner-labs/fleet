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


def _not_found(**kwargs):
    return subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found", **kwargs
    )


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_delete_success(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok(), _not_found(), _ok(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_vcluster_delete_fails_fallback_namespace_delete(
    mock_run, _mock_sleep, monkeypatch
):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok(), _not_found(), _ok(), _fail(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 5
    ns_call = mock_run.call_args_list[4].args[0]
    assert ns_call == [
        "oc",
        "delete",
        "namespace",
        "test-ns",
        "--ignore-not-found=true",
    ]


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_vcluster_delete_fails_fallback_also_fails(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok(), _not_found(), _ok(), _fail(), _fail()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_run.call_count == 5


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_managedcluster_delete_tolerant(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_fail(), _not_found(), _ok(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_waits_for_managedcluster_removal(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok(), _ok(), _ok(), _not_found(), _ok(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_managedcluster_timeout_proceeds(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok()] + [_ok()] * 60 + [_ok(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 63


@mock.patch("fleet.tasks.delete_test_vcluster.time.sleep")
@mock.patch("fleet.tasks.delete_test_vcluster.subprocess.run")
def test_skips_vcluster_delete_when_namespace_gone(mock_run, _mock_sleep, monkeypatch):
    monkeypatch.setenv("FLEET_CONFIGMAP_LOADED", "true")
    mock_run.side_effect = [_ok(), _not_found(), _not_found()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-vc", "--namespace", "test-ns"],
    ):
        main()
    assert mock_run.call_count == 3
