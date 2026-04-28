"""Read the tier label from a ManagedCluster.

CLI: fleet-read-cluster-tier --cluster-name NAME
Prints the tier value to stdout. Exits 1 on failure or empty result.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("read-cluster-tier")

    info("=== Reading ManagedCluster tier label ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info(f"Getting tier label from managedcluster/{cluster}...")
    result = subprocess.run(
        [
            "oc",
            "get",
            "managedcluster",
            cluster,
            "-o",
            "jsonpath={.metadata.labels.tier}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc get tier exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to read tier label: {result.stderr}")
        sys.exit(1)

    tier = result.stdout.strip()
    info(f"  -> tier value: '{tier}' (length: {len(tier)})")
    if not tier:
        error("Tier label is empty on ManagedCluster")
        sys.exit(1)

    print(tier)
