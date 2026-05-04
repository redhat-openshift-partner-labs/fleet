"""Delete a test vCluster and its hub resources."""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("delete-test-vcluster")

    info("=== Deleting test vCluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  namespace={args.namespace}")

    info(f"Deleting ManagedCluster '{cluster}'...")
    result = subprocess.run(
        ["oc", "delete", "managedcluster", cluster, "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    info(f"  -> managedcluster delete exit code: {result.returncode}")

    info(f"Deleting vCluster '{cluster}'...")
    result = subprocess.run(
        [
            "vcluster",
            "delete",
            cluster,
            "-n",
            args.namespace,
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> vcluster delete exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to delete vCluster: {result.stderr}")
        sys.exit(1)

    info("Delete complete")
