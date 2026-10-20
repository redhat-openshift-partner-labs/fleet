"""Bind scoped AWS credentials to the installed cluster's infra ID and VPC (scoped clusters).

CLI: fleet-scope-aws-credentials --cluster-name NAME [--timeout-seconds 600]
Scaffold-rendered policies carry INFRA_ID_PLACEHOLDER / VPC_ID_PLACEHOLDER, which match nothing
until install. This task reads the infra ID from the ClusterDeployment, finds the cluster VPC
(tag kubernetes.io/cluster/<infraID>=owned) with the hub's installer credentials, and substitutes
both into the cluster's Crossplane Policies and Roles. Afterwards resources tagged only with the
installer cluster tag (cloud-controller-manager LBs/SGs, CSI volumes) count as owned, and egress-IP
ENI changes are limited to the cluster VPC. It then waits until the provider's observed AWS state
(status.atProvider) no longer contains placeholders, so a hub identity that cannot update IAM
policies (e.g. missing iam:CreatePolicyVersion) fails here with the Synced message instead of
leaving the cluster fail-closed. Idempotent. Exits 1 on any failure.
"""

import argparse
import binascii
import json
import subprocess
import sys
import time

from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_binding import (
    aws_credentials,
    bind,
    cluster_facts,
    cluster_vpc,
    oc_json,
)
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


def _substitute(target: str, infra_id: str, vpc_id: str) -> bool:
    """Replace placeholders in spec.forProvider; return True if the resource was patched."""
    for_provider = oc_json(target)["spec"]["forProvider"]
    raw = json.dumps(for_provider)
    bound = bind(raw, infra_id, vpc_id)
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


def _unbound(targets: list[str]) -> dict[str, str]:
    """TYPE/NAME -> reason for every target whose observed AWS state still has placeholders."""
    result = subprocess.run(
        ["oc", "get", *targets, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        reason = f"oc get failed: {result.stderr.strip()}"
        return {t: reason for t in targets}

    pending: dict[str, str] = {}
    for item in json.loads(result.stdout).get("items", []):
        status = item.get("status", {})
        observed = json.dumps(status.get("atProvider", {}))
        if INFRA_ID_PLACEHOLDER in observed or VPC_ID_PLACEHOLDER in observed:
            synced = {c["type"]: c for c in status.get("conditions", [])}.get(
                "Synced", {}
            )
            target = f"{item['kind'].lower()}.iam/{item['metadata']['name']}"
            pending[target] = (
                synced.get("message")
                if synced.get("status") == "False"
                else "provider has not applied the update yet"
            )
    return pending


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    configure("scope-aws-credentials")

    cluster = args.cluster_name
    info("=== Binding scoped AWS credentials to the installed cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    try:
        infra_id, region, creds_secret = cluster_facts(cluster)
        info(f"  infraID={infra_id} region={region}")
        key_id, secret = aws_credentials(cluster, creds_secret)
        vpc_id = cluster_vpc(region, key_id, secret, infra_id)
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

    info(
        f"Patched {patched} resource(s); waiting for AWS to reflect the bound policies..."
    )
    targets = policy_targets(cluster)
    elapsed, interval = 0, 10
    while True:
        pending = _unbound(targets)
        if not pending:
            break
        if elapsed >= args.timeout_seconds:
            error(f"Timed out after {elapsed}s; policies not bound in AWS:")
            for target, reason in pending.items():
                error(f"  {target}: {reason}")
            sys.exit(1)
        time.sleep(interval)
        elapsed += interval
        info(f"  Poll [{elapsed}s/{args.timeout_seconds}s]: {len(pending)} pending")

    info(f"Bound {len(targets)} resource(s) to infraID {infra_id} / {vpc_id}")
