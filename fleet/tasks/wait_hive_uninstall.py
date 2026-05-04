"""Wait for Hive to complete cluster uninstall.

CLI: fleet-wait-hive-uninstall --cluster-name NAME [--timeout 25m]
Checks if ClusterDeployment exists; if so, waits for deletion. Exits 1 on timeout.
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
    cluster = resolve_required(args.cluster_name, "cluster-name", "wait-hive-uninstall")
    timeout = resolve(args.timeout, "timeout", "wait-hive-uninstall") or "25m"
    configure("wait-hive-uninstall")

    info("=== Waiting for Hive cluster uninstall to complete ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={timeout}")

    info(f"Checking if ClusterDeployment '{cluster}' still exists in ns '{cluster}'...")
    result = subprocess.run(
        ["oc", "get", "clusterdeployment", cluster, "-n", cluster],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc get exit code: {result.returncode}")
    if result.returncode != 0:
        info(f"ClusterDeployment already gone (Hive uninstall complete)")
        return

    info(
        f"ClusterDeployment still exists, waiting for deletion (timeout: {timeout})..."
    )
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=delete",
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
        error(
            f"Timed out waiting for ClusterDeployment '{cluster}' deletion: {result.stderr}"
        )
        sys.exit(1)

    info(f"ClusterDeployment '{cluster}' deleted (cloud cleanup complete)")
