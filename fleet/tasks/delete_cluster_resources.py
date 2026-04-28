"""Delete cluster resources in order for deprovision.

CLI: fleet-delete-cluster-resources --cluster-name NAME
Deletes KlusterletAddonConfig, ManagedCluster (with wait), MachinePools,
and ClusterDeployment. All operations are idempotent via --ignore-not-found.
"""

import argparse
import subprocess

from fleet.tasks._log import configure, info, warn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("delete-cluster-resources")

    info(f"Deleting cluster resources for {cluster} in explicit order...")

    subprocess.run(
        [
            "oc",
            "delete",
            "klusterletaddonconfig",
            cluster,
            "-n",
            cluster,
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  KlusterletAddonConfig deleted")

    subprocess.run(
        ["oc", "delete", "managedcluster", cluster, "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    info("  ManagedCluster deleted")

    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=delete",
            f"managedcluster/{cluster}",
            "--timeout=5m",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"  ManagedCluster delete wait failed: {result.stderr}")
    else:
        info("  ManagedCluster wait complete")

    subprocess.run(
        [
            "oc",
            "delete",
            "machinepool",
            "-n",
            cluster,
            "--all",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  MachinePools deleted")

    subprocess.run(
        [
            "oc",
            "delete",
            "clusterdeployment",
            cluster,
            "-n",
            cluster,
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  ClusterDeployment delete requested (Hive uninstall will run)")
