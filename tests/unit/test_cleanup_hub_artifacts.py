from unittest import mock

import subprocess

import pytest

from fleet.tasks.cleanup_hub_artifacts import main


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_all_deletions_succeed(mock_run, mock_sleep):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 7
    mock_sleep.assert_called_once_with(15)


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_certificate_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = [
        _run_fail([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 7


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_clusterissuer_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = [
        _run([]),
        _run_fail([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 7


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_crossplane_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = [
        _run([]),
        _run([]),
        _run_fail([]),
        _run_fail([]),
        _run_fail([]),
        _run_fail([]),
        _run([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 7


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_namespace_deletion_fails_exits_1(mock_run, mock_sleep):
    mock_run.side_effect = [
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run([]),
        _run_fail([]),
    ]
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_clusterissuer_uses_letsencrypt_prefix(mock_run, mock_sleep):
    mock_run.return_value = _run([])
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "clusterissuer",
            "letsencrypt-test-cluster",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_sleep_called_after_crossplane_deletes(mock_run, mock_sleep):
    call_order = []

    def track_run(args, **kwargs):
        call_order.append(("run", args))
        return _run(args)

    def track_sleep(seconds):
        call_order.append(("sleep", seconds))

    mock_run.side_effect = track_run
    mock_sleep.side_effect = track_sleep
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    sleep_idx = next(i for i, c in enumerate(call_order) if c[0] == "sleep")
    ns_idx = next(
        i for i, c in enumerate(call_order) if c[0] == "run" and "namespace" in c[1]
    )
    assert sleep_idx < ns_idx
