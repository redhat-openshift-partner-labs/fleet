"""Create the cluster namespace on the hub (idempotent).

CLI: fleet-create-namespace --cluster-name NAME
Creates namespace {cluster} via oc. No-op if it already exists. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._env import resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    args = parser.parse_args()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "create-namespace"
    )

    cluster = args.cluster_name
    configure("create-namespace")

    info("=== Creating cluster namespace ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info(f"Checking if namespace '{cluster}' exists...")
    result = subprocess.run(
        ["oc", "get", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc get namespace/exists exit code: {result.returncode}")
    if result.returncode == 0:
        info(f"Namespace {cluster} already exists")
        return

    info(f"Creating namespace {cluster}...")
    result = subprocess.run(
        ["oc", "create", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc create exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create namespace {cluster}: {result.stderr}")
        sys.exit(1)
    info(f"Namespace {cluster} created")
