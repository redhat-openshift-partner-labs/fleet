"""Wait for the spoke to join ACM as a ManagedCluster.

CLI: fleet-wait-for-managed-cluster --cluster-name NAME [--timeout 15m]
Runs oc wait --for=condition=ManagedClusterJoined on managedcluster/{cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="15m")
    args = parser.parse_args()

    cluster = args.cluster_name

    print(f"Waiting for ManagedCluster {cluster} to join (timeout: {args.timeout})...")
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
        print(f"ManagedCluster {cluster} not joined: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"ManagedCluster {cluster} joined")
