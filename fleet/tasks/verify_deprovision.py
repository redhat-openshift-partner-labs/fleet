"""Verify that deprovision completed cleanly.

CLI: fleet-verify-deprovision --cluster-name NAME
Checks that namespace, ManagedCluster, ClusterDeployment, the hub-side CronJob, and the
cluster's Crossplane IAM resources are all gone.
Exits 1 if any resources remain or the IAM check cannot run.
"""

import argparse
import sys

from fleet.tasks._aws_components import DiscoveryError, all_iam_targets
from fleet.tasks._iam_cleanup import CleanupError, oc
from fleet.tasks._log import configure, info, warn


def _check_gone(resource_type: str, name: str, namespace: str | None = None) -> bool:
    """Require a successful lookup with no matching resource."""
    target = f"{resource_type}/{name}"
    scope = ("-n", namespace) if namespace else ()
    try:
        exists = oc("get", target, *scope, "--ignore-not-found", "-o", "name").strip()
    except CleanupError as exc:
        warn(f"  Could not check {target}: {exc}")
        return False
    if exists:
        warn(f"  {target} in ns {namespace or 'cluster'}: still exists")
        return False
    info(f"  {target} in ns {namespace or 'cluster'}: gone")
    return True


def _iam_remaining(cluster: str) -> list[str] | None:
    """IAM resources still present, or None if the lookup failed."""
    try:
        targets = all_iam_targets(cluster)
        return oc("get", *targets, "--ignore-not-found", "-o", "name").split()
    except (CleanupError, DiscoveryError) as exc:
        warn(f"  Could not check IAM resources: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("verify-deprovision")

    info("=== Verifying clean deprovision ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info("Checking that all cluster resources are gone...")
    errors = 0

    info("Namespace:")
    if not _check_gone("namespace", cluster):
        errors += 1

    info("ManagedCluster:")
    if not _check_gone("managedcluster", cluster):
        errors += 1

    info("ClusterDeployment:")
    if not _check_gone("clusterdeployment", cluster, cluster):
        errors += 1

    info("Hub-side CronJob:")
    if not _check_gone("cronjob", cluster, "default"):
        errors += 1

    info("Crossplane IAM resources:")
    remaining = _iam_remaining(cluster)
    if remaining is None:
        errors += 1
    elif remaining:
        for name in remaining:
            warn(f"  {name}: still exists")
        errors += len(remaining)
    else:
        info("  all gone")

    if errors > 0:
        warn(f"{errors} resources still present. Manual cleanup may be needed.")
        sys.exit(1)
    info("Deprovision verified: hub resources cleaned up")
