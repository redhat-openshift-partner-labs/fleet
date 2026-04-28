"""Apply Hive cluster CRs (ClusterDeployment, MachinePool, ManagedCluster, etc.).

CLI: fleet-apply-cluster-crs --cluster-name NAME --source-dir DIR
Builds clusters/{cluster}/ with kustomize and applies via oc. Exits 1 on build or apply failure.
"""

import argparse
import os
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    source = args.source_dir

    hive_dir = os.path.join(source, "hive")
    configure("apply-cluster-crs")
    info(f"Applying cluster CRs for {cluster}...")
    build = subprocess.run(
        ["kustomize", "build", hive_dir],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        error(f"kustomize build failed: {build.stderr}")
        sys.exit(1)

    apply = subprocess.run(
        ["oc", "apply", "--server-side=true", "--force-conflicts", "-f", "-"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        error(f"oc apply failed: {apply.stderr}")
        sys.exit(1)

    info("Cluster resources applied")
