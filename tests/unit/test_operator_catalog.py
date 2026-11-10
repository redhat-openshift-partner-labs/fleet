import json
import subprocess
from unittest import mock

from fleet.tasks._operator_catalog import check_operator_catalog


def _ok(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


def _manifest(
    package_name: str = "operator",
    source: str = "redhat-operators",
    channel: str = "stable",
    current_csv: str = "operator.v1.0.0",
) -> dict:
    return {
        "metadata": {"name": package_name},
        "status": {
            "packageName": package_name,
            "catalogSource": source,
            "catalogSourceNamespace": "openshift-marketplace",
            "channels": [{"name": channel, "currentCSV": current_csv}],
        },
    }


def _manifest_list(*manifests: dict) -> dict:
    return {"items": list(manifests)}


def _check_catalog(
    mock_retry: mock.Mock,
    response: dict,
    package_name: str = "nfd",
    source: str = "redhat-operators",
) -> tuple[bool, str]:
    mock_retry.return_value = _ok(json.dumps(response))
    return check_operator_catalog(package_name, "stable", source, "kubeconfig")


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_success(mock_retry):
    available, reason = _check_catalog(
        mock_retry, _manifest_list(_manifest(package_name="nfd"))
    )

    assert available is True
    assert reason == "nfd stable is available from redhat-operators"
    mock_retry.assert_called_once_with(
        [
            "oc",
            "get",
            "packagemanifest",
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
def test_check_operator_catalog_selects_matching_source_for_repeated_package(
    mock_retry,
):
    community_manifest = _manifest(
        package_name="authorino-operator",
        source="community-operators",
        channel="beta",
        current_csv="community.v1.0.0",
    )
    community_manifest["metadata"]["name"] += "-community"

    redhat_manifest = _manifest(package_name="authorino-operator")
    redhat_manifest["metadata"]["name"] += "-redhat"

    available, reason = _check_catalog(
        mock_retry,
        _manifest_list(community_manifest, redhat_manifest),
        package_name="authorino-operator",
    )
    assert available is True
    assert reason == "authorino-operator stable is available from redhat-operators"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_wrong_source(mock_retry):
    manifest = _manifest(package_name="nfd", source="certified-operators")
    available, reason = _check_catalog(mock_retry, _manifest_list(manifest))

    assert available is False
    assert (
        reason == "nfd is available from certified-operators, expected redhat-operators"
    )


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_package_missing_from_catalog_list(mock_retry):
    available, reason = _check_catalog(mock_retry, _manifest_list())

    assert available is False
    assert reason == "nfd is not available from any catalog"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_missing_channel(mock_retry):
    manifest = _manifest(package_name="nfd")
    manifest["status"]["channels"] = [{"name": "beta", "currentCSV": "operator.v1.0.0"}]
    available, reason = _check_catalog(mock_retry, _manifest_list(manifest))

    assert available is False
    assert reason == "nfd does not provide channel stable"


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_wrong_namespace(mock_retry):
    manifest = _manifest(package_name="nfd")
    manifest["status"]["catalogSourceNamespace"] = "other-marketplace"
    available, reason = _check_catalog(mock_retry, _manifest_list(manifest))

    assert available is False
    assert reason == (
        "nfd is available from other-marketplace, expected openshift-marketplace"
    )


@mock.patch("fleet.tasks._operator_catalog.run_with_retry")
def test_check_operator_catalog_rejects_channel_without_csv(mock_retry):
    manifest = _manifest(package_name="nfd")
    manifest["status"]["channels"] = [{"name": "stable", "currentCSV": ""}]
    available, reason = _check_catalog(mock_retry, _manifest_list(manifest))

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
