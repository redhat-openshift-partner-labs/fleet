"""Bind scaffold-rendered AWS placeholders to an installed cluster's infra ID and VPC.

Shared by scope-aws-credentials (binds the live Crossplane resources after install) and
apply-crossplane-creds (binds the rendered overlay before a re-apply, so a re-run never
re-asserts the placeholders on an installed cluster).
"""

import base64
import json
import subprocess

import boto3

from fleet.tasks._aws_components import INFRA_ID_PLACEHOLDER, VPC_ID_PLACEHOLDER


def oc_json(*args: str) -> dict:
    result = subprocess.run(
        ["oc", "get", *args, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def cluster_facts(cluster: str) -> tuple[str, str, str]:
    """(infraID, region, credentials secret name) from the ClusterDeployment."""
    spec = oc_json("clusterdeployment", cluster, "-n", cluster)["spec"]
    infra_id = (spec.get("clusterMetadata") or {}).get("infraID", "")
    if not infra_id:
        raise ValueError(f"ClusterDeployment {cluster} has no infraID (not installed?)")
    aws = spec["platform"]["aws"]
    return infra_id, aws["region"], aws["credentialsSecretRef"]["name"]


def aws_credentials(cluster: str, secret: str) -> tuple[str, str]:
    data = oc_json("secret", secret, "-n", cluster)["data"]
    return (
        base64.b64decode(data["aws_access_key_id"]).decode(),
        base64.b64decode(data["aws_secret_access_key"]).decode(),
    )


def cluster_vpc(region: str, key_id: str, secret: str, infra_id: str) -> str:
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


def bind(text: str, infra_id: str, vpc_id: str) -> str:
    """Replace both placeholders in *text*."""
    return text.replace(INFRA_ID_PLACEHOLDER, infra_id).replace(
        VPC_ID_PLACEHOLDER, vpc_id
    )
