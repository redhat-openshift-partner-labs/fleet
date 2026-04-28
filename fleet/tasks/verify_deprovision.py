"""Verify that deprovision completed cleanly.

CLI: fleet-verify-deprovision --cluster-name NAME
Checks that namespace, ManagedCluster, and ClusterDeployment are all gone.
Exits 1 if any resources remain.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, info, warn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("verify-deprovision")

    errors = 0

    info(f"Verifying clean deprovision for {cluster}...")

    result = subprocess.run(
        ["oc", "get", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        warn(f"  FAIL Namespace {cluster} still exists")
        errors += 1
    else:
        info(f"  OK Namespace {cluster} gone")

    result = subprocess.run(
        ["oc", "get", "managedcluster", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        warn(f"  FAIL ManagedCluster {cluster} still exists")
        errors += 1
    else:
        info(f"  OK ManagedCluster {cluster} gone")

    result = subprocess.run(
        ["oc", "get", "clusterdeployment", cluster, "-n", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        warn(f"  FAIL ClusterDeployment {cluster} still exists")
        errors += 1
    else:
        info(f"  OK ClusterDeployment {cluster} gone")

    if errors > 0:
        warn(f"{errors} resources still present. Manual cleanup may be needed.")
        sys.exit(1)

    info("Deprovision verified: all resources cleaned up")
