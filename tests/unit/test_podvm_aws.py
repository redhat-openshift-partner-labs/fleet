from unittest import mock

import pytest
from botocore.exceptions import ClientError

from fleet.tasks._aws_components import CLUSTER_LABEL
from fleet.tasks._podvm_aws import (
    PODVM_PORTS,
    UEFI_BOOT_MODES,
    PodVMError,
    ec2_client,
    instance_id,
    node_network,
    open_podvm_ports,
    pod_vm_instances,
    terminate,
)

REGION = "us-east-2"
LIVE_STATES = ["pending", "running", "stopping", "stopped", "shutting-down"]


def _client_error(code, operation="AuthorizeSecurityGroupIngress"):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def test_scaffold_contract_strings():
    """The operator documents the ports; AMD SEV-SNP needs a UEFI boot mode."""
    assert PODVM_PORTS == (("tcp", 15150), ("tcp", 9000), ("udp", 9000))
    assert UEFI_BOOT_MODES == ("uefi", "uefi-preferred")


# ---------------------------------------------------------------------------
# Client and node lookups
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks._podvm_aws.aws_credentials")
@mock.patch("fleet.tasks._podvm_aws.boto3")
def test_ec2_client_uses_the_cluster_credential(mock_boto3, mock_credentials):
    mock_credentials.return_value = ("AKIAEXAMPLE", "s3cr3t")
    assert ec2_client("c1", REGION, "aws-credentials") is mock_boto3.client.return_value
    mock_credentials.assert_called_once_with("c1", "aws-credentials")
    mock_boto3.client.assert_called_once_with(
        "ec2",
        region_name=REGION,
        aws_access_key_id="AKIAEXAMPLE",
        aws_secret_access_key="s3cr3t",
    )


def test_instance_id_from_provider_id():
    assert instance_id("aws:///us-east-2a/i-0abc") == "i-0abc"


@pytest.mark.parametrize(
    "provider_id", ["azure:///x", "", "aws:///us-east-2a/", "aws:///i-0abc"]
)
def test_instance_id_rejects_other_provider_ids(provider_id):
    with pytest.raises(PodVMError) as exc:
        instance_id(provider_id)
    assert str(exc.value) == f"unexpected providerID '{provider_id}'"


def test_node_network():
    ec2 = mock.MagicMock()
    ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-0abc",
                        "VpcId": "vpc-1",
                        "SubnetId": "subnet-1",
                        "SecurityGroups": [
                            {"GroupId": "sg-a", "GroupName": "node"},
                            {"GroupId": "sg-b", "GroupName": "lb"},
                        ],
                    }
                ]
            }
        ]
    }
    assert node_network(ec2, "i-0abc") == ("vpc-1", "subnet-1", ["sg-a", "sg-b"])
    ec2.describe_instances.assert_called_once_with(InstanceIds=["i-0abc"])


@pytest.mark.parametrize("answer", [{"Reservations": []}, {"Reservations": [{}]}])
def test_node_network_fails_without_an_instance(answer):
    ec2 = mock.MagicMock()
    ec2.describe_instances.return_value = answer
    with pytest.raises(PodVMError) as exc:
        node_network(ec2, "i-0abc")
    assert str(exc.value) == "instance i-0abc not found"


# ---------------------------------------------------------------------------
# Security group rules for pod VM traffic
# ---------------------------------------------------------------------------


def _ingress_call(group, protocol, port):
    return mock.call(
        GroupId=group,
        IpPermissions=[
            {
                "IpProtocol": protocol,
                "FromPort": port,
                "ToPort": port,
                "UserIdGroupPairs": [{"GroupId": group}],
            }
        ],
    )


def test_open_podvm_ports_authorizes_each_port_on_each_group():
    ec2 = mock.MagicMock()
    assert open_podvm_ports(ec2, ["sg-a", "sg-b"]) == 6
    assert ec2.authorize_security_group_ingress.call_args_list == [
        _ingress_call(group, protocol, port)
        for group in ("sg-a", "sg-b")
        for protocol, port in PODVM_PORTS
    ]


def test_open_podvm_ports_counts_an_existing_rule_as_present():
    ec2 = mock.MagicMock()
    ec2.authorize_security_group_ingress.side_effect = [
        None,
        _client_error("InvalidPermission.Duplicate"),
        None,
    ]
    assert open_podvm_ports(ec2, ["sg-a"]) == 2
    assert ec2.authorize_security_group_ingress.call_count == 3


def test_open_podvm_ports_propagates_other_errors():
    ec2 = mock.MagicMock()
    ec2.authorize_security_group_ingress.side_effect = _client_error(
        "UnauthorizedOperation"
    )
    with pytest.raises(ClientError):
        open_podvm_ports(ec2, ["sg-a"])
    assert ec2.authorize_security_group_ingress.call_count == 1


def test_open_podvm_ports_without_groups():
    ec2 = mock.MagicMock()
    assert open_podvm_ports(ec2, []) == 0
    ec2.authorize_security_group_ingress.assert_not_called()


# ---------------------------------------------------------------------------
# Pod VMs: live instances with an ownership tag and no instance profile
# ---------------------------------------------------------------------------


def _instance(instance, state="running", profile=False):
    item = {"InstanceId": instance, "State": {"Name": state}}
    if profile:
        item["IamInstanceProfile"] = {"Arn": "arn:aws:iam::1:instance-profile/worker"}
    return item


def _pages(*pages):
    """One paginate() answer: each page is a list of instances in one reservation."""
    return [{"Reservations": [{"Instances": list(page)}]} for page in pages]


def test_pod_vm_instances_queries_both_ownership_tags():
    ec2 = mock.MagicMock()
    paginate = ec2.get_paginator.return_value.paginate
    paginate.side_effect = [_pages(), _pages()]
    assert pod_vm_instances(ec2, "c1", "c1-abcde") == {}
    ec2.get_paginator.assert_called_once_with("describe_instances")
    states = {"Name": "instance-state-name", "Values": LIVE_STATES}
    assert paginate.call_args_list == [
        mock.call(Filters=[{"Name": f"tag:{CLUSTER_LABEL}", "Values": ["c1"]}, states]),
        mock.call(
            Filters=[
                {"Name": "tag:kubernetes.io/cluster/c1-abcde", "Values": ["owned"]},
                states,
            ]
        ),
    ]


def test_pod_vm_instances_leave_out_nodes_and_merge_both_queries():
    ec2 = mock.MagicMock()
    ec2.get_paginator.return_value.paginate.side_effect = [
        # Ownership label: a node, and two pod VMs across two pages
        _pages(
            [_instance("i-node", profile=True), _instance("i-pod-1")],
            [_instance("i-pod-2", "shutting-down")],
        ),
        # Infra ID tag: the node again, one pod VM again, one new
        _pages(
            [
                _instance("i-node", profile=True),
                _instance("i-pod-1"),
                _instance("i-pod-3", "pending"),
            ]
        ),
    ]
    assert pod_vm_instances(ec2, "c1", "c1-abcde") == {
        "i-pod-1": "running",
        "i-pod-2": "shutting-down",
        "i-pod-3": "pending",
    }


def test_pod_vm_instances_tolerates_empty_pages():
    ec2 = mock.MagicMock()
    ec2.get_paginator.return_value.paginate.side_effect = [
        [{"Reservations": []}, {}],
        [{"Reservations": [{}]}],
    ]
    assert pod_vm_instances(ec2, "c1", "c1-abcde") == {}


def test_terminate():
    ec2 = mock.MagicMock()
    terminate(ec2, ["i-1", "i-2"])
    ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-1", "i-2"])


def test_terminate_nothing():
    ec2 = mock.MagicMock()
    terminate(ec2, [])
    ec2.terminate_instances.assert_not_called()
