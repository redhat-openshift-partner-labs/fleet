from unittest import mock

import base64
import json
import subprocess

import pytest

from fleet.tasks._aws_components import INFRA_ID_PLACEHOLDER, VPC_ID_PLACEHOLDER
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


# ---------------------------------------------------------------------------
# Re-applies keep an installed scoped cluster bound to its infra ID and VPC
# ---------------------------------------------------------------------------

INFRA, VPC = "c1-ab3de", "vpc-0123456789abcdef0"
KEY_ID, SECRET = "AKIAINSTALLER", "installer/secret"
RENDERED = (
    f'policy: \'{{"tag": "kubernetes.io/cluster/{INFRA_ID_PLACEHOLDER}",'
    f' "vpc": "vpc/{VPC_ID_PLACEHOLDER}"}}\'\n'
)


def _cd(infra=INFRA):
    spec = {
        "clusterMetadata": {"infraID": infra} if infra else {},
        "platform": {
            "aws": {
                "region": "us-east-2",
                "credentialsSecretRef": {"name": "aws-credentials"},
            }
        },
    }
    return _ok(stdout=json.dumps({"spec": spec}))


def _creds():
    data = {
        "aws_access_key_id": base64.b64encode(KEY_ID.encode()).decode(),
        "aws_secret_access_key": base64.b64encode(SECRET.encode()).decode(),
    }
    return _ok(stdout=json.dumps({"data": data}))


def _ec2(vpcs):
    client = mock.Mock()
    client.describe_vpcs.return_value = {"Vpcs": [{"VpcId": v} for v in vpcs]}
    return client


def _main():
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "c1", "--source-dir", "/src"]
    ):
        main()


@mock.patch("fleet.tasks._aws_binding.subprocess.run")
@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_output_without_placeholders_skips_cluster_lookup(mock_retry, mock_run):
    mock_retry.side_effect = [_ok(stdout="kind: User"), _ok(stdout="applied")]
    _main()
    mock_run.assert_not_called()
    assert mock_retry.call_args_list[1].kwargs["input"] == "kind: User"


@pytest.mark.parametrize("cd", [_ok(stdout=""), _cd(infra="")])
@mock.patch("fleet.tasks._aws_binding.subprocess.run")
@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_not_installed_applies_placeholders(mock_retry, mock_run, cd):
    """First run (no ClusterDeployment) or install pending: nothing to bind yet."""
    mock_retry.side_effect = [_ok(stdout=RENDERED), _ok(stdout="applied")]
    mock_run.return_value = cd
    _main()
    assert mock_run.call_args.args[0][:4] == ["oc", "get", "clusterdeployment", "c1"]
    assert "--ignore-not-found" in mock_run.call_args.args[0]
    assert mock_retry.call_args_list[1].kwargs["input"] == RENDERED


@mock.patch("fleet.tasks.apply_crossplane_creds.info")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks._aws_binding.subprocess.run")
@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_installed_cluster_is_bound_before_apply(
    mock_retry, mock_run, mock_boto3, mock_info
):
    mock_retry.side_effect = [_ok(stdout=RENDERED), _ok(stdout="applied")]
    mock_run.side_effect = [_cd(), _creds()]
    mock_boto3.client.return_value = _ec2([VPC])
    _main()
    applied = mock_retry.call_args_list[1].kwargs["input"]
    assert INFRA_ID_PLACEHOLDER not in applied and VPC_ID_PLACEHOLDER not in applied
    assert f"kubernetes.io/cluster/{INFRA}" in applied and f"vpc/{VPC}" in applied
    logged = " ".join(str(c) for c in mock_info.call_args_list)
    assert INFRA in logged and VPC in logged
    assert KEY_ID not in logged and SECRET not in logged


@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks._aws_binding.subprocess.run")
@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_installed_cluster_binding_failure_never_applies(
    mock_retry, mock_run, mock_boto3
):
    mock_retry.side_effect = [_ok(stdout=RENDERED)]
    mock_run.side_effect = [_cd(), _creds()]
    mock_boto3.client.return_value = _ec2([])
    with pytest.raises(SystemExit, match="1"):
        _main()
    assert mock_retry.call_count == 1


@mock.patch("fleet.tasks._aws_binding.subprocess.run")
@mock.patch("fleet.tasks.apply_crossplane_creds.run_with_retry")
def test_cluster_deployment_read_failure_never_applies(mock_retry, mock_run):
    """An API error proves nothing about install state; don't risk unbinding a live cluster."""
    mock_retry.side_effect = [_ok(stdout=RENDERED)]
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="timeout")
    with pytest.raises(SystemExit, match="1"):
        _main()
    assert mock_retry.call_count == 1
