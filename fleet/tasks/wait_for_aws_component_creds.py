"""Wait until a scoped AWS cluster's Crossplane IAM resources are usable.

CLI: fleet-wait-for-aws-component-creds --cluster-name NAME [--timeout-seconds 600]
Polls every 10s until every <cluster>-<operator>-credentials-raw Secret exists in namespace
{cluster} AND every Crossplane IAM resource of the cluster (installer and operator users,
policies, attachments, access keys, BYO node roles) reports Ready=True. The installer needs the
node roles to exist before provisioning. On timeout, logs missing Secrets and each unready
resource with its Synced message (e.g. an AWS AccessDenied), then exits 1.
"""

import argparse
import json
import subprocess
import sys
import time

from fleet.tasks._aws_components import COMPONENTS, iam_targets, raw_secret_name
from fleet.tasks._log import configure, error, info


def _secrets_present(cluster: str, secrets: list[str]) -> bool:
    # A single get fails until every named Secret exists
    result = subprocess.run(
        ["oc", "get", "secret", *secrets, "-n", cluster, "-o", "name"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _unready_resources(cluster: str) -> dict[str, str]:
    """TYPE/NAME -> reason for every cluster IAM resource that is missing or not Ready."""
    targets = iam_targets(cluster)
    result = subprocess.run(
        ["oc", "get", *targets, "--ignore-not-found", "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        reason = f"oc get failed: {result.stderr.strip()}"
        return {t: reason for t in targets}

    ready: set[str] = set()
    reasons: dict[str, str] = {}
    for item in json.loads(result.stdout or "{}").get("items", []):
        target = f"{item['kind'].lower()}.iam/{item['metadata']['name']}"
        conditions = {
            c["type"]: c for c in item.get("status", {}).get("conditions", [])
        }
        if conditions.get("Ready", {}).get("status") == "True":
            ready.add(target)
        else:
            reasons[target] = conditions.get("Synced", {}).get("message") or "not Ready"
    return {t: reasons.get(t, "not found") for t in targets if t not in ready}


def _report(cluster: str, secrets: list[str]) -> None:
    result = subprocess.run(
        ["oc", "get", "secret", *secrets, "-n", cluster, "-o", "name"],
        capture_output=True,
        text=True,
    )
    present = {line.split("/", 1)[-1] for line in result.stdout.split()}
    missing = [s for s in secrets if s not in present]
    if missing:
        error(f"Missing Secrets in ns '{cluster}': {', '.join(missing)}")
    for target, reason in _unready_resources(cluster).items():
        error(f"  {target}: {reason}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    configure("wait-for-aws-component-creds")

    cluster = args.cluster_name
    secrets = [raw_secret_name(cluster, c.key) for c in COMPONENTS]
    info("=== Waiting for scoped AWS IAM resources and credential Secrets ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={args.timeout_seconds}s")
    info(f"  secrets={len(secrets)} iam-resources={len(iam_targets(cluster))}")

    timeout = args.timeout_seconds
    elapsed = 0
    interval = 10

    while elapsed < timeout:
        # Resources are only queried once the Secrets exist (one oc call per round until then)
        if _secrets_present(cluster, secrets):
            pending = _unready_resources(cluster)
            if not pending:
                info(
                    f"All Secrets present and IAM resources Ready (elapsed: {elapsed}s)"
                )
                return
            info(f"  {len(pending)} IAM resource(s) not Ready yet")

        time.sleep(interval)
        elapsed += interval
        info(f"  Poll [{elapsed}s/{timeout}s]: not ready yet")

    error(f"Timed out after {timeout}s waiting for scoped AWS credentials")
    _report(cluster, secrets)
    sys.exit(1)
