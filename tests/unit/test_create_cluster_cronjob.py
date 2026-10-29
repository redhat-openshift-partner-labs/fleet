from unittest import mock

import pytest
import subprocess
import yaml

from fleet.tasks.create_cluster_cronjob import _cronjob, main
from fleet.tasks._schedule import schedule_error, timezone_error

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--timezone",
    "America/Chicago",
    "--schedule",
    "00 08 * * 1-5",
]


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="failed")


@mock.patch("fleet.tasks.create_cluster_cronjob.run_with_retry")
@mock.patch("fleet.tasks.create_cluster_cronjob.subprocess.run")
def test_cronjob_is_created_in_default_namespace(mock_run, mock_retry):
    mock_run.return_value = _run(["oc", "get", "serviceaccount", "ecoeng"])
    mock_retry.return_value = _run(["oc", "apply"])
    with mock.patch("sys.argv", BASE_ARGV):
        main()

    manifest = yaml.safe_load(mock_retry.call_args.kwargs["input"])
    assert manifest["kind"] == "CronJob"
    assert manifest["metadata"] == {"name": "test-cluster", "namespace": "default"}
    spec = manifest["spec"]
    assert spec["schedule"] == "00 08 * * 1-5"
    assert spec["timeZone"] == "America/Chicago"
    pod_spec = spec["jobTemplate"]["spec"]["template"]["spec"]
    assert pod_spec["serviceAccountName"] == "ecoeng"
    assert "serviceAccount" not in pod_spec
    assert pod_spec["containers"][0]["command"][-1] == "test-cluster"


def test_cronjob_uses_required_handler_settings():
    manifest = _cronjob("test-cluster", "America/Chicago", "00 08 * * 1-5")
    container = manifest["spec"]["jobTemplate"]["spec"]["template"]["spec"][
        "containers"
    ][0]
    assert container["image"] == "quay.io/rhopl/osplc:v0.0.2"
    assert container["imagePullPolicy"] == "Always"
    assert manifest["spec"]["successfulJobsHistoryLimit"] == 3
    assert manifest["spec"]["failedJobsHistoryLimit"] == 1


@mock.patch("fleet.tasks.create_cluster_cronjob.subprocess.run")
def test_missing_service_account_fails_before_apply(mock_run):
    mock_run.return_value = _run_fail(["oc", "get", "serviceaccount", "ecoeng"])
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_called_once()


@mock.patch("fleet.tasks.create_cluster_cronjob.run_with_retry")
@mock.patch("fleet.tasks.create_cluster_cronjob.subprocess.run")
def test_apply_failure_exits_1(mock_run, mock_retry):
    mock_run.return_value = _run(["oc", "get", "serviceaccount", "ecoeng"])
    mock_retry.return_value = _run_fail(["oc", "apply"])
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_invalid_timezone_exits_1():
    argv = [*BASE_ARGV[:4], "Not/AZone", *BASE_ARGV[5:]]
    with mock.patch("sys.argv", argv):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_invalid_schedule_exits_1():
    argv = [*BASE_ARGV[:-1], "00 08 * *"]
    with mock.patch("sys.argv", argv):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_timezone_error_accepts_non_string():
    assert "expected an IANA timezone name" in timezone_error(42)


def test_schedule_error_accepts_non_string():
    assert "expected a five-field cron expression" in schedule_error(42)


def test_schedule_error_rejects_invalid_field_syntax():
    assert "invalid cron field" in schedule_error("00 08 * * Monday")


def test_schedule_error_rejects_zero_step():
    assert "zero step" in schedule_error("00/0 08 * * 1-5")
