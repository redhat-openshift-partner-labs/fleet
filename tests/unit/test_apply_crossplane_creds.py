from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_crossplane_creds import main


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "yaml-output", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_apply_success(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="apiVersion: v1\nkind: User"),
        _ok(stdout="applied"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        main()
    assert mock_retry.call_count == 2
    mock_retry.assert_any_call(
        ["kustomize", "build", "/src/crossplane"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_uses_server_side_apply(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="yaml"),
        _ok(stdout="applied"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        main()
    apply_call = mock_retry.call_args_list[1]
    assert "--server-side=true" in apply_call.args[0]
    assert "--force-conflicts" in apply_call.args[0]


@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_kustomize_build_fails(mock_retry):
    mock_retry.return_value = _fail()
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_oc_apply_fails(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="yaml-content"),
        _fail(stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/src"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
