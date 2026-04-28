"""Wait for the spoke to join ACM as a ManagedCluster.

CLI: fleet-wait-for-managed-cluster --cluster-name NAME [--timeout 15m]
Runs oc wait --for=condition=ManagedClusterJoined on managedcluster/{cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="15m")
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("wait-for-managed-cluster")

    info(f"Waiting for ManagedCluster {cluster} to join (timeout: {args.timeout})...")
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=ManagedClusterJoined",
            f"managedcluster/{cluster}",
            f"--timeout={args.timeout}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"ManagedCluster {cluster} not joined: {result.stderr}")
        sys.exit(1)

    info(f"ManagedCluster {cluster} joined")
