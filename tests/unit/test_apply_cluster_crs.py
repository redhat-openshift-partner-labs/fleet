from unittest import mock

import subprocess

import pytest

from fleet.tasks.apply_cluster_crs import main


def _ok(**overrides):
    defaults = {"args": [], "returncode": 0, "stdout": "yaml-output", "stderr": ""}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


def _fail(**overrides):
    defaults = {"args": [], "returncode": 1, "stdout": "", "stderr": "error"}
    defaults.update(overrides)
    return subprocess.CompletedProcess(**defaults)


@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_apply_success(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="yaml-output"),
        _ok(stdout="applied"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        main()
    assert mock_retry.call_count == 2
    mock_retry.assert_any_call(
        ["kustomize", "build", "/repo/hive"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_kustomize_fails(mock_retry):
    mock_retry.return_value = _fail()
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_oc_apply_fails(mock_retry):
    mock_retry.side_effect = [
        _ok(stdout="yaml"),
        _fail(stderr="forbidden"),
    ]
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


# ---------------------------------------------------------------------------
# Guard: a referenced Hive manifests Secret must exist before applying
# ---------------------------------------------------------------------------

SCOPED_OVERLAY = """\
apiVersion: v1
kind: Namespace
metadata:
  name: test-cluster
---
apiVersion: hive.openshift.io/v1
kind: ClusterDeployment
metadata:
  name: test-cluster
  namespace: test-cluster
spec:
  provisioning:
    manifestsSecretRef:
      name: test-cluster-cloud-credentials-manifests
"""

ARGV = ["prog", "--cluster-name", "test-cluster", "--source-dir", "/repo"]


@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_applies_when_manifests_secret_exists(mock_retry, mock_run):
    mock_retry.side_effect = [_ok(stdout=SCOPED_OVERLAY), _ok(stdout="applied")]
    mock_run.return_value = _ok(
        stdout="secret/test-cluster-cloud-credentials-manifests"
    )
    with mock.patch("sys.argv", ARGV):
        main()
    mock_run.assert_called_once_with(
        [
            "oc",
            "get",
            "secret",
            "test-cluster-cloud-credentials-manifests",
            "-n",
            "test-cluster",
            "-o",
            "name",
        ],
        capture_output=True,
        text=True,
    )
    assert mock_retry.call_count == 2


@mock.patch("fleet.tasks.apply_cluster_crs.error")
@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_refuses_to_apply_when_manifests_secret_missing(
    mock_retry, mock_run, mock_error
):
    mock_retry.side_effect = [_ok(stdout=SCOPED_OVERLAY)]
    mock_run.return_value = _fail(stderr="NotFound")
    with mock.patch("sys.argv", ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    # oc apply never ran, so Hive never starts an install that cannot succeed
    assert mock_retry.call_count == 1
    messages = " ".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "test-cluster-cloud-credentials-manifests" in messages


@mock.patch("fleet.tasks.apply_cluster_crs.subprocess.run")
@mock.patch("fleet.tasks.apply_cluster_crs.run_with_retry")
def test_no_check_without_manifests_ref(mock_retry, mock_run):
    legacy = (
        SCOPED_OVERLAY.split("  provisioning:")[0] + "  clusterName: test-cluster\n"
    )
    mock_retry.side_effect = [_ok(stdout=legacy), _ok(stdout="applied")]
    with mock.patch("sys.argv", ARGV):
        main()
    mock_run.assert_not_called()
