"""Delete cluster resources in order for deprovision.

CLI: fleet-delete-cluster-resources --cluster-name NAME
Deletes KlusterletAddonConfig, ManagedCluster (with wait), MachinePools,
and ClusterDeployment. All operations are idempotent via --ignore-not-found.
"""

import argparse
import subprocess

from fleet.tasks._env import resolve_required
from fleet.tasks._log import configure, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    args = parser.parse_args()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "delete-cluster-resources"
    )

    cluster = args.cluster_name
    configure("delete-cluster-resources")

    info("=== Deleting cluster resources ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info("Deleting KlusterletAddonConfig...")
    result = subprocess.run(
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
    info(f"  -> KlusterletAddonConfig/{cluster}: exit code {result.returncode}")

    info("Deleting ManagedCluster...")
    result = subprocess.run(
        ["oc", "delete", "managedcluster", cluster, "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    info(f"  -> ManagedCluster/{cluster}: exit code {result.returncode}")

    info(f"Waiting up to 5m for ManagedCluster/{cluster} to be deleted...")
    result = subprocess.run(
        ["oc", "wait", "--for=delete", f"managedcluster/{cluster}", "--timeout=5m"],
        capture_output=True,
        text=True,
    )
    info(f"  -> Wait exit code: {result.returncode}")
    info("  -> Wait complete")

    info(f"Deleting MachinePools in ns {cluster}...")
    result = subprocess.run(
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
    info(f"  -> MachinePool: exit code {result.returncode}")

    info(f"Deleting ClusterDeployment/{cluster} in ns {cluster}...")
    result = subprocess.run(
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
    info(f"  -> ClusterDeployment/{cluster}: exit code {result.returncode}")

    info("Cluster resources deleted")
