"""Label the ManagedCluster as provisioned to signal post-provision readiness.

CLI: fleet-label-post-provision --cluster-name NAME
Sets provisioned=true on managedcluster/{cluster}. Exits 1 on failure.
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
        args.cluster_name, "cluster-name", "label-post-provision"
    )

    cluster = args.cluster_name
    configure("label-post-provision")

    info("=== Labeling ManagedCluster as provisioned ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  label=provisioned=true (overwrite)")

    info(f"Running: oc label managedcluster/{cluster} provisioned=true --overwrite...")
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
    info(f"  -> oc label exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to label ManagedCluster: {result.stderr}")
        sys.exit(1)
    info("ManagedCluster provisioned=true labeled")
