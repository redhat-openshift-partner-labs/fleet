"""EC2 lookups and changes for peer pod VMs, made on the hub with the cluster's installer credential.

prepare-podvm-aws reads the network of a worker node and opens the pod VM ports (node_network,
open_podvm_ports). terminate-pod-vms finds and terminates the pod VMs before the cluster is
uninstalled (pod_vm_instances, terminate). The pod VM image is built and deleted by
fleet.tasks._podvm_image_aws.
"""

import re
from typing import Any

import boto3
from botocore.exceptions import ClientError

from fleet.tasks._aws_binding import aws_credentials
from fleet.tasks._aws_components import CLUSTER_LABEL

# agent-protocol-forwarder, and VXLAN (the Red Hat procedure opens tcp; VXLAN is UDP)
PODVM_PORTS = (("tcp", 15150), ("tcp", 9000), ("udp", 9000))
# Boot modes of an AMI that AMD SEV-SNP can launch
UEFI_BOOT_MODES = ("uefi", "uefi-preferred")

# Every state before terminated
_LIVE_STATES = ["pending", "running", "stopping", "stopped", "shutting-down"]
# Node.spec.providerID on AWS: aws:///<availability zone>/<instance ID>
_PROVIDER_ID = re.compile(r"aws:///[^/]+/(i-[0-9a-f]+)")


class PodVMError(RuntimeError):
    """A pod VM prerequisite is missing or an EC2 answer is unusable."""


def ec2_client(cluster: str, region: str, creds_secret: str) -> Any:
    """boto3 EC2 client for region with the credential in Secret creds_secret (aws_credentials)."""
    key_id, secret = aws_credentials(cluster, creds_secret)
    return boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )


def instance_id(provider_id: str) -> str:
    """ "aws:///us-east-2a/i-0abc" -> "i-0abc". PodVMError for any other shape."""
    match = _PROVIDER_ID.fullmatch(provider_id)
    if not match:
        raise PodVMError(f"unexpected providerID '{provider_id}'")
    return match.group(1)


def node_network(ec2: Any, instance: str) -> tuple[str, str, list[str]]:
    """(VpcId, SubnetId, [GroupId, ...]) of the instance, from DescribeInstances.

    PodVMError when the answer holds no instance.
    """
    reservations = ec2.describe_instances(InstanceIds=[instance])["Reservations"]
    instances = [i for r in reservations for i in r.get("Instances", [])]
    if not instances:
        raise PodVMError(f"instance {instance} not found")
    found = instances[0]
    groups = [group["GroupId"] for group in found["SecurityGroups"]]
    return found["VpcId"], found["SubnetId"], groups


def open_podvm_ports(ec2: Any, sg_ids: list[str]) -> int:
    """Authorize PODVM_PORTS on each group, source the same group; returns the number of rules added.

    A rule that already exists (InvalidPermission.Duplicate) is not counted; any other
    ClientError propagates.
    """
    added = 0
    for group in sg_ids:
        for protocol, port in PODVM_PORTS:
            try:
                ec2.authorize_security_group_ingress(
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
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                    raise
            else:
                added += 1
    return added


def pod_vm_instances(ec2: Any, cluster: str, infra_id: str) -> dict[str, str]:
    """InstanceId -> state of every pod VM of the cluster.

    A pod VM is an instance in a state before terminated that carries the ownership tag
    <CLUSTER_LABEL>=<cluster> or kubernetes.io/cluster/<infra_id>=owned and has no IAM instance
    profile. Cluster nodes carry the same tags and always have a profile; the peer-pods
    credential cannot attach one.
    """
    paginator = ec2.get_paginator("describe_instances")
    states = {"Name": "instance-state-name", "Values": _LIVE_STATES}
    ownership = (
        {"Name": f"tag:{CLUSTER_LABEL}", "Values": [cluster]},
        {"Name": f"tag:kubernetes.io/cluster/{infra_id}", "Values": ["owned"]},
    )
    found: dict[str, str] = {}
    for tag in ownership:
        for page in paginator.paginate(Filters=[tag, states]):
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    if not instance.get("IamInstanceProfile"):
                        found[instance["InstanceId"]] = instance["State"]["Name"]
    return found


def terminate(ec2: Any, ids: list[str]) -> None:
    """TerminateInstances(InstanceIds=ids); no call for an empty list."""
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
