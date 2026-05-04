"""Delete a test vCluster and its hub resources."""

import argparse
import subprocess
import sys
import time

from fleet.tasks._env import check_configmap_env, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--namespace", default=None)
    args = parser.parse_args()

    check_configmap_env()
    cluster = resolve_required(
        args.cluster_name, "cluster-name", "delete-test-vcluster"
    )
    args.namespace = resolve_required(
        args.namespace, "namespace", "delete-test-vcluster"
    )
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

    info("Waiting for ManagedCluster to be fully removed...")
    for _ in range(60):
        result = subprocess.run(
            ["oc", "get", "managedcluster", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            info("  -> ManagedCluster gone")
            break
        time.sleep(5)
    else:
        info("  -> ManagedCluster still present after 300s, proceeding anyway")

    result = subprocess.run(
        ["oc", "get", "namespace", args.namespace],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        info(f"Namespace '{args.namespace}' already removed, skipping vcluster delete")
        info("Delete complete")
        return

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
        info(
            f"vcluster delete failed ({result.stderr.strip()}), falling back to namespace delete"
        )
        result = subprocess.run(
            ["oc", "delete", "namespace", args.namespace, "--ignore-not-found=true"],
            capture_output=True,
            text=True,
        )
        info(f"  -> namespace delete exit code: {result.returncode}")
        if result.returncode != 0:
            error(f"Failed to delete namespace: {result.stderr}")
            sys.exit(1)

    info("Delete complete")
