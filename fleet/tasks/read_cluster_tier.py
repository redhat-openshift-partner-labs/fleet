"""Read the tier label from a ManagedCluster.

CLI: fleet-read-cluster-tier --cluster-name NAME
Prints the tier value to stdout. Exits 1 on failure or empty result.
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
    if result.returncode != 0:
        print(f"Failed to read tier label: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    tier = result.stdout.strip()
    if not tier:
        print("Tier label is empty on ManagedCluster", file=sys.stderr)
        sys.exit(1)

    print(tier)
