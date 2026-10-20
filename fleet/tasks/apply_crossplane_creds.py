"""Apply Crossplane IAM resources for a cluster via kustomize build + oc apply.

CLI: fleet-apply-crossplane-creds --cluster-name NAME --source-dir DIR
Builds the cluster's crossplane overlay with kustomize and applies the output. Exits 1 on build or apply failure.

The force-conflicts apply takes back every field in the overlay. On an installed scoped cluster that
would re-assert INFRA_ID_PLACEHOLDER/VPC_ID_PLACEHOLDER over the values scope-aws-credentials bound,
cutting the live cluster's credentials off. So when the cluster is already installed, the rendered
overlay is bound to its infra ID and VPC before applying. If binding fails, nothing is applied.
"""

import argparse
import binascii
import os
import subprocess
import sys

from botocore.exceptions import BotoCoreError, ClientError

from fleet._retry import run_with_retry
from fleet.tasks._aws_binding import (
    aws_credentials,
    bind,
    cluster_vpc,
    installed_cluster_facts,
)
from fleet.tasks._aws_components import INFRA_ID_PLACEHOLDER, VPC_ID_PLACEHOLDER
from fleet.tasks._log import configure, error, info


def _bind_if_installed(cluster: str, rendered: str) -> str:
    """Return *rendered* with placeholders bound if the cluster is installed, else unchanged."""
    if INFRA_ID_PLACEHOLDER not in rendered and VPC_ID_PLACEHOLDER not in rendered:
        return rendered
    facts = installed_cluster_facts(cluster)
    if facts is None:
        info("  -> Cluster not installed yet; applying placeholders")
        return rendered
    infra_id, region, creds_secret = facts
    key_id, secret = aws_credentials(cluster, creds_secret)
    vpc_id = cluster_vpc(region, key_id, secret, infra_id)
    info(f"  -> Cluster installed; binding infraID={infra_id} vpc={vpc_id}")
    return bind(rendered, infra_id, vpc_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    source = args.source_dir

    crossplane_dir = os.path.join(source, "crossplane")
    configure("apply-crossplane-creds")

    info("=== Applying Crossplane IAM resources ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={source}")
    info(f"  crossplane-dir={crossplane_dir}")

    info(f"Running kustomize build on {crossplane_dir}...")
    build = run_with_retry(
        ["kustomize", "build", crossplane_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)
    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} YAML documents")

    try:
        manifests = _bind_if_installed(cluster, build.stdout)
    except subprocess.CalledProcessError as exc:
        error(f"oc command failed; not applying: {exc.stderr}")
        sys.exit(1)
    except (
        ValueError,
        KeyError,
        binascii.Error,
        ClientError,
        BotoCoreError,
    ) as exc:
        error(f"Cannot bind the installed cluster's credentials; not applying: {exc}")
        sys.exit(1)

    info("Applying Crossplane resources...")
    apply = run_with_retry(
        ["oc", "apply", "--server-side=true", "--force-conflicts", "-f", "-"],
        input=manifests,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")
    info("Crossplane IAM resources applied")
