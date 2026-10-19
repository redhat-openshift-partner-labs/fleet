from unittest import mock

import base64
import json
import subprocess

import pytest
from botocore.exceptions import ClientError

from fleet.tasks._aws_components import (
    COMPONENTS,
    INFRA_ID_PLACEHOLDER,
    VPC_ID_PLACEHOLDER,
)
from fleet.tasks.scope_aws_credentials import main, policy_targets

INFRA, VPC, REGION = "c1-ab3de", "vpc-0123456789abcdef0", "us-east-2"
KEY_ID, SECRET = "AKIAINSTALLER", "installer/secret"
TARGETS = policy_targets("c1")


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


def test_policy_targets_cover_operator_policies_and_node_roles():
    assert TARGETS == [f"policy.iam/c1-{c.key}-policy" for c in COMPONENTS] + [
        "role.iam/c1-master-role",
        "role.iam/c1-worker-role",
    ]


@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_substitutes_infra_id_and_vpc(mock_run, mock_boto3):
    mock_boto3.client.return_value = _ec2([VPC])
    gets_and_patches = []
    for _ in TARGETS:
        gets_and_patches += [_iam_resource(), _ok()]
    mock_run.side_effect = [
        _cluster_deployment(),
        _creds_secret(),
        *gets_and_patches,
        _observed(),
    ]
    with _argv():
        main()
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
@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_idempotent_and_credentials_never_on_argv_or_logged(
    mock_run, mock_boto3, mock_info
):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = [
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
    mock_run.side_effect = [_cluster_deployment(infra="")]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_cluster_deployment_read_failure_exits(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="nope")
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@pytest.mark.parametrize("vpcs", [[], [VPC, "vpc-other"]])
@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_requires_exactly_one_cluster_vpc(mock_run, mock_boto3, vpcs):
    mock_boto3.client.return_value = _ec2(vpcs)
    mock_run.side_effect = [_cluster_deployment(), _creds_secret()]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_aws_api_error_exits(mock_run, mock_boto3):
    mock_boto3.client.return_value.describe_vpcs.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
        "DescribeVpcs",
    )
    mock_run.side_effect = [_cluster_deployment(), _creds_secret()]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_patch_failure_exits(mock_run, mock_boto3):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = [
        _cluster_deployment(),
        _creds_secret(),
        _iam_resource(),
        subprocess.CalledProcessError(1, "oc", stderr="denied"),
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


def _bound_run(*verify_results):
    """Side effects: facts, creds, already-bound resources (no patches), then verify reads."""
    return [
        _cluster_deployment(),
        _creds_secret(),
        *[_iam_resource(with_placeholders=False) for _ in TARGETS],
        *verify_results,
    ]


@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
@mock.patch("fleet.tasks.scope_aws_credentials.subprocess.run")
def test_waits_until_aws_reflects_bound_policies(mock_run, mock_boto3, mock_sleep):
    mock_boto3.client.return_value = _ec2([VPC])
    mock_run.side_effect = _bound_run(_observed(bound=False), _observed())
    with _argv():
        main()
    mock_sleep.assert_called_once_with(10)


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
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
    assert "policy.iam/c1-machine-api-policy" in messages
    assert denied in messages


@mock.patch("fleet.tasks.scope_aws_credentials.error")
@mock.patch("fleet.tasks.scope_aws_credentials.time.sleep")
@mock.patch("fleet.tasks.scope_aws_credentials.boto3")
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
