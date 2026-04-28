"""Label the ManagedCluster as provisioned to signal post-provision readiness.

CLI: fleet-label-post-provision --cluster-name NAME
Sets provisioned=true on managedcluster/{cluster}. Exits 1 on failure.
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
    configure("label-post-provision")

    result = subprocess.run(
        [
            "oc",
            "label",
            f"managedcluster/{cluster}",
            "provisioned=true",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to label ManagedCluster: {result.stderr}")
        sys.exit(1)

    info(f"ManagedCluster {cluster} labeled provisioned=true")
