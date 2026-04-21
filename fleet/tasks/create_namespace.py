"""Create the cluster namespace on the hub (idempotent).

CLI: fleet-create-namespace --cluster-name NAME
Creates namespace {cluster} via oc. No-op if it already exists. Exits 1 on failure.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    result = subprocess.run(
        ["oc", "get", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"Namespace {cluster} already exists")
        return

    result = subprocess.run(
        ["oc", "create", "namespace", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to create namespace {cluster}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"Namespace {cluster} created")
