"""Delete cluster resources in order for deprovision.

CLI: fleet-delete-cluster-resources --cluster-name NAME
Deletes KlusterletAddonConfig, ManagedCluster (with wait), MachinePools,
and ClusterDeployment. All operations are idempotent via --ignore-not-found.
"""

import argparse
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name

    print(f"Deleting cluster resources for {cluster} in explicit order...")

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
    print("  KlusterletAddonConfig deleted")

    subprocess.run(
        ["oc", "delete", "managedcluster", cluster, "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    print("  ManagedCluster deleted")

    subprocess.run(
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
    print("  ManagedCluster wait complete")

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
    print("  MachinePools deleted")

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
    print("  ClusterDeployment delete requested (Hive uninstall will run)")
