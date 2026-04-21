"""Wait for Hive to complete cluster uninstall.

CLI: fleet-wait-hive-uninstall --cluster-name NAME [--timeout 25m]
Checks if ClusterDeployment exists; if so, waits for deletion. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="25m")
    args = parser.parse_args()

    cluster = args.cluster_name

    print(f"Waiting for Hive uninstall to complete (timeout: {args.timeout})...")

    result = subprocess.run(
        [
            "oc",
            "get",
            "clusterdeployment",
            cluster,
            "-n",
            cluster,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ClusterDeployment {cluster} already gone")
        return

    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=delete",
            f"clusterdeployment/{cluster}",
            "-n",
            cluster,
            f"--timeout={args.timeout}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"Timed out waiting for ClusterDeployment {cluster} deletion: {result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"ClusterDeployment {cluster} deleted (cloud cleanup complete)")
