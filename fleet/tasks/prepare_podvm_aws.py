"""Resolve the network and image of peer pod VMs and open their ports (coco tier, AWS).

CLI: fleet-prepare-podvm-aws --cluster-name NAME --spoke-kubeconfig PATH
Reads the cluster's region and installer credential from the hub, takes the first worker node
of the spoke by name and reads its VPC, subnet and security groups from EC2. Finds the pod VM
AMI by tag, then authorizes the pod VM ports on those security groups. Prints one JSON object
to stdout: region, vpc-id, subnet-id, sg-ids (comma-separated), ami-id. Log lines go to stderr.
Exits 1 on any failure; a missing or unusable AMI fails before a security group rule is added.
"""

import argparse
import binascii
import json
import subprocess
import sys

from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_binding import cluster_facts
from fleet.tasks._log import configure, error, info
from fleet.tasks._podvm_aws import (
    PodVMError,
    ec2_client,
    instance_id,
    node_network,
    open_podvm_ports,
    podvm_image,
)


def _first_worker_instance(spoke_kubeconfig: str) -> str:
    """Instance ID of the first node with role worker, by name."""
    result = subprocess.run(
        [
            "oc",
            "get",
            "nodes",
            "-l",
            "node-role.kubernetes.io/worker",
            "-o",
            "json",
            f"--kubeconfig={spoke_kubeconfig}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    nodes = sorted(
        json.loads(result.stdout).get("items", []),
        key=lambda node: node["metadata"]["name"],
    )
    if not nodes:
        raise PodVMError("no node with role worker on the spoke")
    info(f"  -> worker node: {nodes[0]['metadata']['name']}")
    return instance_id(nodes[0]["spec"].get("providerID", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    configure("prepare-podvm-aws")

    cluster = args.cluster_name
    info("=== Preparing the pod VM network and image ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    try:
        _, region, creds_secret = cluster_facts(cluster)
        ec2 = ec2_client(cluster, region, creds_secret)
        instance = _first_worker_instance(args.spoke_kubeconfig)
        vpc_id, subnet_id, sg_ids = node_network(ec2, instance)
        info(f"  -> {instance}: vpc={vpc_id} subnet={subnet_id} sgs={','.join(sg_ids)}")
        ami_id = podvm_image(ec2, region)
        info(f"  -> pod VM AMI: {ami_id}")
        added = open_podvm_ports(ec2, sg_ids)
        info(f"  -> pod VM ports: {added} rule(s) added")
    except subprocess.CalledProcessError as exc:
        error(
            f"Failed to prepare the pod VM network and image: {exc}: "
            f"{(exc.stderr or '').strip()}"
        )
        sys.exit(1)
    except (
        PodVMError,
        ValueError,
        KeyError,
        binascii.Error,
        ClientError,
        BotoCoreError,
    ) as exc:
        error(f"Failed to prepare the pod VM network and image: {exc}")
        sys.exit(1)

    print(
        json.dumps(
            {
                "region": region,
                "vpc-id": vpc_id,
                "subnet-id": subnet_id,
                "sg-ids": ",".join(sg_ids),
                "ami-id": ami_id,
            }
        )
    )
