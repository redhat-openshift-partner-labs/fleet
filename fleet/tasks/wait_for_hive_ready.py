"""Wait for Hive to finish provisioning the cluster.

CLI: fleet-wait-for-hive-ready --cluster-name NAME [--timeout 60m]
Runs oc wait --for=condition=Provisioned on ClusterDeployment/{cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--timeout", default=None)
    args = parser.parse_args()

    check_configmap_env()
    configure("wait-for-hive-ready")

    cluster = resolve_required(args.cluster_name, "cluster-name", "wait-for-hive-ready")
    timeout = resolve(args.timeout, "timeout", "wait-for-hive-ready") or "60m"
    info("=== Waiting for Hive to provision cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={timeout}")

    info(f"Waiting for ClusterDeployment '{cluster}' to reach Provisioned condition...")
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=Provisioned",
            f"clusterdeployment/{cluster}",
            "-n",
            cluster,
            f"--timeout={timeout}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc wait exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"ClusterDeployment not provisioned: {result.stderr}")
        sys.exit(1)
    info(f"Cluster '{cluster}' provisioned successfully")
