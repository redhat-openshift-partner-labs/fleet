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

    configure("wait-for-hive-ready")

    cluster = args.cluster_name
    info("=== Waiting for Hive to provision cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={args.timeout}")

    info(f"Waiting for ClusterDeployment '{cluster}' to reach Provisioned condition...")
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
    info(f"  -> oc wait exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"ClusterDeployment not provisioned: {result.stderr}")
        sys.exit(1)
    info(f"Cluster '{cluster}' provisioned successfully")
