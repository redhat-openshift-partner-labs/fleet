"""Wait for Hive to complete cluster uninstall.

CLI: fleet-wait-hive-uninstall --cluster-name NAME [--timeout 25m]
Checks if ClusterDeployment exists; if so, waits for deletion. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="25m")
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("wait-hive-uninstall")

    info(f"Waiting for Hive uninstall to complete (timeout: {args.timeout})...")

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
        info("ClusterDeployment already gone")
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
        error(
            f"Timed out waiting for ClusterDeployment {cluster} deletion: {result.stderr}"
        )
        sys.exit(1)

    info("ClusterDeployment deleted (cloud cleanup complete)")
