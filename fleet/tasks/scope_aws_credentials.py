"""Bind scoped AWS credentials to the installed cluster's infra ID and VPC (scoped clusters).

CLI: fleet-scope-aws-credentials --cluster-name NAME
Scaffold-rendered policies carry INFRA_ID_PLACEHOLDER / VPC_ID_PLACEHOLDER, which match nothing
until install. This task reads the infra ID from the ClusterDeployment, finds the cluster VPC
(tag kubernetes.io/cluster/<infraID>=owned) with the hub's installer credentials, and substitutes
both into the cluster's Crossplane Policies and Roles. Afterwards resources tagged only with the
installer cluster tag (cloud-controller-manager LBs/SGs, CSI volumes) count as owned, and egress-IP
ENI changes are limited to the cluster VPC. Idempotent. Exits 1 on any failure.
"""

import argparse
import base64
import binascii
import json
import subprocess
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_components import (
    COMPONENTS,
    INFRA_ID_PLACEHOLDER,
    VPC_ID_PLACEHOLDER,
)
from fleet.tasks._log import configure, error, info


def policy_targets(cluster: str) -> list[str]:
    """Crossplane IAM resources whose policies may contain placeholders."""
    return [f"policy.iam/{cluster}-{c.key}-policy" for c in COMPONENTS] + [
        f"role.iam/{cluster}-master-role",
        f"role.iam/{cluster}-worker-role",
    ]


def _oc_json(*args: str) -> dict:
    result = subprocess.run(
        ["oc", "get", *args, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _cluster_facts(cluster: str) -> tuple[str, str, str]:
    """(infraID, region, credentials secret name) from the ClusterDeployment."""
    spec = _oc_json("clusterdeployment", cluster, "-n", cluster)["spec"]
    infra_id = (spec.get("clusterMetadata") or {}).get("infraID", "")
    if not infra_id:
        raise ValueError(f"ClusterDeployment {cluster} has no infraID (not installed?)")
    aws = spec["platform"]["aws"]
    return infra_id, aws["region"], aws["credentialsSecretRef"]["name"]


def _aws_credentials(cluster: str, secret: str) -> tuple[str, str]:
    data = _oc_json("secret", secret, "-n", cluster)["data"]
    return (
        base64.b64decode(data["aws_access_key_id"]).decode(),
        base64.b64decode(data["aws_secret_access_key"]).decode(),
    )


def _cluster_vpc(region: str, key_id: str, secret: str, infra_id: str) -> str:
    ec2 = boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )
    vpcs = ec2.describe_vpcs(
        Filters=[{"Name": f"tag:kubernetes.io/cluster/{infra_id}", "Values": ["owned"]}]
    )["Vpcs"]
    if len(vpcs) != 1:
        raise ValueError(f"Expected 1 VPC owned by {infra_id}, found {len(vpcs)}")
    return vpcs[0]["VpcId"]


def _substitute(target: str, infra_id: str, vpc_id: str) -> bool:
    """Replace placeholders in spec.forProvider; return True if the resource was patched."""
    for_provider = _oc_json(target)["spec"]["forProvider"]
    raw = json.dumps(for_provider)
    bound = raw.replace(INFRA_ID_PLACEHOLDER, infra_id).replace(
        VPC_ID_PLACEHOLDER, vpc_id
    )
    if bound == raw:
        return False
    patch = json.dumps({"spec": {"forProvider": json.loads(bound)}})
    subprocess.run(
        ["oc", "patch", target, "--type=merge", f"-p={patch}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    configure("scope-aws-credentials")

    cluster = args.cluster_name
    info("=== Binding scoped AWS credentials to the installed cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    try:
        infra_id, region, creds_secret = _cluster_facts(cluster)
        info(f"  infraID={infra_id} region={region}")
        key_id, secret = _aws_credentials(cluster, creds_secret)
        vpc_id = _cluster_vpc(region, key_id, secret, infra_id)
        info(f"  vpc={vpc_id}")

        patched = 0
        for target in policy_targets(cluster):
            if _substitute(target, infra_id, vpc_id):
                info(f"  -> {target}: placeholders substituted")
                patched += 1
            else:
                info(f"  -> {target}: already bound")
    except subprocess.CalledProcessError as exc:
        error(f"oc command failed: {exc.stderr}")
        sys.exit(1)
    except (
        ValueError,
        KeyError,
        binascii.Error,
        ClientError,
        BotoCoreError,
    ) as exc:
        error(f"Failed to bind scoped AWS credentials: {exc}")
        sys.exit(1)

    info(f"Bound {patched} resource(s) to infraID {infra_id} / {vpc_id}")
