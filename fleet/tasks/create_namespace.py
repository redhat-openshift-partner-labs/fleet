"""Create the cluster namespace on the hub (idempotent).

CLI: fleet-create-namespace --cluster-name NAME
Creates namespace {cluster} via oc. No-op if it already exists. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info, warn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("create-namespace")
    result = subprocess.run(
        ["oc", "get", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        warn(f"Namespace {cluster} already exists")
        return

    result = subprocess.run(
        ["oc", "create", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to create namespace: {result.stderr}")
        sys.exit(1)
    info(f"Namespace {cluster} created")
