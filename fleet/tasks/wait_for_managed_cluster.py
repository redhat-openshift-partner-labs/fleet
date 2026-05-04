"""Wait for the spoke to join ACM as a ManagedCluster.

CLI: fleet-wait-for-managed-cluster --cluster-name NAME [--timeout 15m]
Runs oc wait --for=condition=ManagedClusterJoined on managedcluster/{cluster}. Exits 1 on timeout.
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
    configure("wait-for-managed-cluster")

    cluster = resolve_required(
        args.cluster_name, "cluster-name", "wait-for-managed-cluster"
    )
    timeout = resolve(args.timeout, "timeout", "wait-for-managed-cluster") or "15m"
    info("=== Waiting for ManagedCluster to join ACM ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={timeout}")

    info(
        f"Waiting for ManagedCluster '{cluster}' to join (condition: ManagedClusterJoined)..."
    )
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=ManagedClusterJoined",
            f"managedcluster/{cluster}",
            f"--timeout={timeout}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc wait exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"ManagedCluster not joined: {result.stderr}")
        sys.exit(1)
    info(f"ManagedCluster '{cluster}' joined")
