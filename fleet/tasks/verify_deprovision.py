"""Verify that deprovision completed cleanly.

CLI: fleet-verify-deprovision --cluster-name NAME
Checks that namespace, ManagedCluster, ClusterDeployment, and the cluster's Crossplane IAM
resources (known names plus anything with the ownership label) are all gone.
Exits 1 if any resources remain or the IAM check cannot run.
"""

import argparse
import subprocess
import sys

from fleet.tasks._aws_components import all_iam_targets
from fleet.tasks._log import configure, info, warn


def _check_gone(resource_type: str, name: str, namespace: str | None = None) -> bool:
    """Check that a resource is gone. Returns True if gone, False if exists."""
    if namespace:
        result = subprocess.run(
            ["oc", "get", resource_type, name, "-n", namespace],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["oc", "get", resource_type, name],
            capture_output=True,
            text=True,
        )
    if result.returncode == 0:
        warn(f"  {resource_type}/{name} in ns {namespace or 'cluster'}: still exists")
        return False
    info(f"  {resource_type}/{name} in ns {namespace or 'cluster'}: gone")
    return True


def _iam_remaining(cluster: str) -> list[str] | None:
    """IAM resources still present, or None if oc failed (nothing proven gone)."""
    result = subprocess.run(
        ["oc", "get", *all_iam_targets(cluster), "--ignore-not-found", "-o", "name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"  Could not check IAM resources: {result.stderr.strip()}")
        return None
    return result.stdout.split()


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
    info("Deprovision verified: all resources cleaned up")
