"""Wait for Hive to finish provisioning the cluster.

CLI: fleet-wait-for-hive-ready --cluster-name NAME [--timeout 60m]
Runs oc wait --for=condition=Provisioned on ClusterDeployment/{cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="60m")
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("wait-for-hive-ready")

    info(
        f"Waiting for ClusterDeployment {cluster} to be provisioned (timeout: {args.timeout})..."
    )
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=Provisioned",
            f"clusterdeployment/{cluster}",
            "-n",
            cluster,
            f"--timeout={args.timeout}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"ClusterDeployment {cluster} not provisioned: {result.stderr}")
        sys.exit(1)

    info(f"Cluster {cluster} provisioned successfully")
