import json
import subprocess
from unittest import mock

from fleet.tasks._operator_catalog import check_operator_catalog


def _ok(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


def _manifest(
    source: str = "redhat-operators",
    channel: str = "stable",
    current_csv: str = "operator.v1.0.0",
) -> dict:
    return {
        "status": {
            "catalogSource": source,
            "catalogSourceNamespace": "openshift-marketplace",
            "channels": [{"name": channel, "currentCSV": current_csv}],
        }
    }


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_success(mock_retry):
    mock_retry.return_value = _ok(json.dumps(_manifest()))

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is True
    assert reason == "nfd stable is available from redhat-operators"
    mock_retry.assert_called_once_with(
        [
            "oc",
            "get",
            "packagemanifest",
            "nfd",
            "-n",
            "openshift-marketplace",
            "-o",
            "json",
            "--kubeconfig=kubeconfig",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_wrong_source(mock_retry):
    manifest = _manifest(source="certified-operators")
    mock_retry.return_value = _ok(json.dumps(manifest))

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert (
        reason == "nfd is available from certified-operators, expected redhat-operators"
    )


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_missing_channel(mock_retry):
    manifest = _manifest()
    manifest["status"]["channels"] = [{"name": "beta", "currentCSV": "operator.v1.0.0"}]
    mock_retry.return_value = _ok(json.dumps(manifest))

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert reason == "nfd does not provide channel stable"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_wrong_namespace(mock_retry):
    manifest = _manifest()
    manifest["status"]["catalogSourceNamespace"] = "other-marketplace"
    mock_retry.return_value = _ok(json.dumps(manifest))

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert reason == (
        "nfd is available from other-marketplace, expected openshift-marketplace"
    )


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_channel_without_csv(mock_retry):
    manifest = _manifest()
    manifest["status"]["channels"] = [{"name": "stable", "currentCSV": ""}]
    mock_retry.return_value = _ok(json.dumps(manifest))

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert reason == "nfd channel stable has no current ClusterServiceVersion"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_reports_missing_package(mock_retry):
    mock_retry.return_value = _fail("package manifests.config not found")

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert reason == "failed to query nfd: package manifests.config not found"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_reports_invalid_json(mock_retry):
    mock_retry.return_value = _ok("invalid json")

    available, reason = check_operator_catalog(
        "nfd", "stable", "redhat-operators", "kubeconfig"
    )

    assert available is False
    assert (
        reason
        == "failed to parse nfd PackageManifest: Expecting value: line 1 column 1 (char 0)"
    )
