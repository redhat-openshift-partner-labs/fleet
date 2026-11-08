from unittest import mock

import base64
import json
import subprocess

import pytest
from botocore.exceptions import ClientError

from fleet.tasks._aws_components import (
    CLUSTER_LABEL,
    INFRA_ID_PLACEHOLDER,
    REGENERATE,
    VPC_ID_PLACEHOLDER,
)
from fleet.tasks.scope_aws_credentials import main, policy_targets

INFRA, VPC, REGION = "c1-ab3de", "vpc-0123456789abcdef0", "us-east-2"
KEY_ID, SECRET = "AKIAINSTALLER", "installer/secret"
# What `oc get policies,roles -l <label>=c1 -o name` lists for a scoped overlay with one
# operator: the operator policy, the installer policy and the two BYO node roles
LABELLED = [
    "policy.iam.aws.upbound.io/c1-ingress-policy",
    "policy.iam.aws.upbound.io/c1-openshift4installerpolicy",
    "role.iam.aws.upbound.io/c1-master-role",
    "role.iam.aws.upbound.io/c1-worker-role",
]
TARGETS = [
    "policy.iam/c1-ingress-policy",
    "policy.iam/c1-openshift4installerpolicy",
    "role.iam/c1-master-role",
    "role.iam/c1-worker-role",
]
INSTALLER_POLICY = "policy.iam/c1-openshift4installerpolicy"


def _cp(obj, returncode=0):
    return subprocess.CompletedProcess(
        [], returncode=returncode, stdout=json.dumps(obj), stderr="boom"
    )


def _cluster_deployment(infra=INFRA):
    return _cp(
        {
            "spec": {
                "clusterMetadata": {"infraID": infra} if infra else {},
                "platform": {
                    "aws": {
                        "region": REGION,
                        "credentialsSecretRef": {"name": "aws-credentials"},
                    }
                },
            }
        }
    )


def _creds_secret():
    return _cp(
        {
            "data": {
                "aws_access_key_id": base64.b64encode(KEY_ID.encode()).decode(),
                "aws_secret_access_key": base64.b64encode(SECRET.encode()).decode(),
            }
        }
    )


def _iam_resource(with_placeholders=True):
    tag = f"kubernetes.io/cluster/{INFRA_ID_PLACEHOLDER}" if with_placeholders else "x"
    vpc = VPC_ID_PLACEHOLDER if with_placeholders else "vpc-x"
    policy = json.dumps(
        {"Condition": {"tag": tag, "vpc": f"arn:aws:ec2:*:*:vpc/{vpc}"}}
    )
    return _cp({"spec": {"forProvider": {"policy": policy, "tags": {"a": "b"}}}})


def _ok():
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")


def _labelled(stdout=None, returncode=0):
    """The labelled Policy/Role listing policy_targets consumes: the first oc call of a run."""
    if stdout is None:
        stdout = "".join(f"{name}\n" for name in LABELLED)
    return subprocess.CompletedProcess(
        [], returncode=returncode, stdout=stdout, stderr="boom"
    )


def _observed(bound=True, synced_message=""):
    """oc get <targets> -o json: what the provider last read back from AWS."""
    tag = INFRA if bound else INFRA_ID_PLACEHOLDER
    items = []
    for target in TARGETS:
        kind, name = target.split("/", 1)
        doc = json.dumps({"tag": f"kubernetes.io/cluster/{tag}"})
        at_provider = (
            {"inlinePolicy": [{"name": "p", "policy": doc}]}
            if kind == "role.iam"
            else {"policy": doc}
        )
        items.append(
            {
                "kind": "Role" if kind == "role.iam" else "Policy",
                "metadata": {"name": name},
                "status": {
                    "atProvider": at_provider,
                    "conditions": [
                        {
                            "type": "Synced",
                            "status": "False" if synced_message else "True",
                            "message": synced_message,
                        }
                    ],
                },
            }
        )
    return _cp({"kind": "List", "items": items})


def _ec2(vpcs):
    client = mock.Mock()
    client.describe_vpcs.return_value = {"Vpcs": [{"VpcId": v} for v in vpcs]}
    return client


def _argv():
    return mock.patch("sys.argv", ["prog", "--cluster-name", "c1"])


@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_policy_targets_query_and_normalize(mock_run):
    mock_run.return_value = _labelled()
    assert policy_targets("c1") == TARGETS
    mock_run.assert_called_once_with(
        [
            "oc",
            "get",
            "policies.iam.aws.upbound.io,roles.iam.aws.upbound.io",
            "-l",
            f"{CLUSTER_LABEL}=c1",
            "-o",
            "name",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_policy_targets_empty_exits(mock_run, mock_error):
    """An overlay rendered before the ownership label binds nothing: fail, do not skip."""
    mock_run.side_effect = [_labelled(stdout="")]
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert mock_run.call_count == 1
    messages = " ".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "no labelled Policies or Roles for c1" in messages
    assert REGENERATE in messages


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_policy_targets_lookup_failure_exits(mock_run, mock_error):
    mock_run.side_effect = [_labelled(returncode=1)]
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert mock_run.call_count == 1
    messages = " ".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "IAM label lookup failed for c1: boom" in messages


@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_substitutes_infra_id_and_vpc(mock_run, mock_boto3):
    mock_boto3.client.return_value = _ec2([VPC])
    gets_and_patches = []
    for _ in TARGETS:
        gets_and_patches += [_iam_resource(), _ok()]
    mock_run.side_effect = [
        _labelled(),
        _cluster_deployment(),
        _creds_secret(),
        *gets_and_patches,
        _observed(),
    ]
    with _argv():
        main()
    # The wait loop polls the same labelled list the substitution loop walked
    assert mock_run.call_args_list[-1] == mock.call(
        ["oc", "get", *TARGETS, "-o", "json"], capture_output=True, text=True
    )

    mock_boto3.client.assert_called_once_with(
        "ec2",
        region_name=REGION,
        aws_access_key_id=KEY_ID,
        aws_secret_access_key=SECRET,
    )
    mock_boto3.client.return_value.describe_vpcs.assert_called_once_with(
        Filters=[{"Name": f"tag:kubernetes.io/cluster/{INFRA}", "Values": ["owned"]}]
    )
    patches = [c for c in mock_run.call_args_list if c.args[0][1] == "patch"]
    assert [c.args[0][2] for c in patches] == TARGETS
    body = json.loads(patches[0].args[0][4].removeprefix("-p="))
    policy = body["spec"]["forProvider"]["policy"]
    assert INFRA_ID_PLACEHOLDER not in policy and VPC_ID_PLACEHOLDER not in policy
    assert f"kubernetes.io/cluster/{INFRA}" in policy and f"vpc/{VPC}" in policy
    assert body["spec"]["forProvider"]["tags"] == {"a": "b"}


@mock.patch("fleet.tasks.scope_aws_credentials.info")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_installer_policy_is_already_bound(mock_run, mock_boto3, mock_info):
    """The installer policy carries no placeholders: listed, read, left alone."""
    mock_boto3.client.return_value = _ec2([VPC])
    gets_and_patches = []
    for target in TARGETS:
        if target == INSTALLER_POLICY:
            gets_and_patches.append(_iam_resource(with_placeholders=False))
        else:
            gets_and_patches += [_iam_resource(), _ok()]
    mock_run.side_effect = [
        _labelled(),
        _cluster_deployment(),
        _creds_secret(),
        *gets_and_patches,
        _observed(),
    ]
    with _argv():
        main()
    patched = [c.args[0][2] for c in mock_run.call_args_list if c.args[0][1] == "patch"]
    assert patched == [t for t in TARGETS if t != INSTALLER_POLICY]
    logged = [str(c.args[0]) for c in mock_info.call_args_list]
    assert f"  -> {INSTALLER_POLICY}: already bound" in logged
    assert f"  -> {TARGETS[0]}: placeholders substituted" in logged


@mock.patch("fleet.tasks.scope_aws_credentials.info")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_idempotent_and_credentials_never_on_argv_or_logged(
    mock_run, mock_boto3, mock_info
):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = [
        _labelled(),
        _cluster_deployment(),
        _creds_secret(),
        *[_iam_resource(with_placeholders=False) for _ in TARGETS],
        _observed(),
    ]
    with _argv():
        main()
    assert not [c for c in mock_run.call_args_list if c.args[0][1] == "patch"]
    for call in mock_run.call_args_list:
        assert SECRET not in " ".join(call.args[0])
    logged = " ".join(str(c.args[0]) for c in mock_info.call_args_list)
    assert SECRET not in logged and KEY_ID not in logged


@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_missing_infra_id_exits(mock_run):
    mock_run.side_effect = [_labelled(), _cluster_deployment(infra="")]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_cluster_deployment_read_failure_exits(mock_run):
    mock_run.side_effect = [
        _labelled(),
        subprocess.CalledProcessError(1, "oc", stderr="nope"),
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@pytest.mark.parametrize("vpcs", [[], [VPC, "vpc-other"]])
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_requires_exactly_one_cluster_vpc(mock_run, mock_boto3, vpcs):
    mock_boto3.client.return_value = _ec2(vpcs)
    mock_run.side_effect = [_labelled(), _cluster_deployment(), _creds_secret()]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_aws_api_error_exits(mock_run, mock_boto3):
    mock_boto3.client.return_value.describe_vpcs.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
        "DescribeVpcs",
    )
    mock_run.side_effect = [_labelled(), _cluster_deployment(), _creds_secret()]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_patch_failure_exits(mock_run, mock_boto3):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = [
        _labelled(),
        _cluster_deployment(),
        _creds_secret(),
        _iam_resource(),
        subprocess.CalledProcessError(1, "oc", stderr="denied"),
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


def _bound_run(*verify_results):
    """Side effects: listing, facts, creds, already-bound resources (no patches), then verify reads."""
    return [
        _labelled(),
        _cluster_deployment(),
        _creds_secret(),
        *[_iam_resource(with_placeholders=False) for _ in TARGETS],
        *verify_results,
    ]


@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_waits_until_aws_reflects_bound_policies(mock_run, mock_boto3, mock_sleep):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = _bound_run(_observed(bound=False), _observed())
    with _argv():
        main()
    mock_sleep.assert_called_once_with(10)


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_timeout_reports_synced_message(mock_run, mock_boto3, mock_sleep, mock_error):
    """Missing hub permissions (e.g. CreatePolicyVersion) fail here, not silently."""
    denied = "AccessDenied: not authorized to perform: iam:CreatePolicyVersion"
    mock_boto3.client.return_value = _ec2([VPC])
    pending = _observed(bound=False, synced_message=denied)
    mock_run.side_effect = _bound_run(pending, pending)
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "c1", "--timeout-seconds", "10"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    messages = "\n".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "policy.iam/c1-ingress-policy" in messages
    assert denied in messages


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks._aws_binding.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_verification_query_failure_times_out(
    mock_run, mock_boto3, mock_sleep, mock_error
):
    mock_boto3.client.return_value = _ec2([VPC])
    failed = _cp({}, returncode=1)
    mock_run.side_effect = _bound_run(failed, failed)
    with mock.patch(
        "sys.argv", ["prog", "--cluster-name", "c1", "--timeout-seconds", "10"]
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert "oc get failed" in " ".join(
        str(c.args[0]) for c in mock_error.call_args_list
    )
