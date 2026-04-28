"""Verify that deprovision completed cleanly.

CLI: fleet-verify-deprovision --cluster-name NAME
Checks that namespace, ManagedCluster, and ClusterDeployment are all gone.
Exits 1 if any resources remain.
"""

import argparse
import subprocess
import sys

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

    if errors > 0:
        warn(f"{errors} resources still present. Manual cleanup may be needed.")
        sys.exit(1)
    info("Deprovision verified: all resources cleaned up")
