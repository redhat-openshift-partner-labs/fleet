"""Apply Hive cluster CRs (ClusterDeployment, MachinePool, ManagedCluster, etc.).

CLI: fleet-apply-cluster-crs --cluster-name NAME --source-dir DIR
Builds clusters/{cluster}/ with kustomize and applies via oc. Exits 1 on build or apply failure.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    source = args.source_dir
    cluster_dir = f"{source}/clusters/{cluster}"

    print(f"Applying cluster CRs for {cluster}...")
    build = subprocess.run(
        ["kustomize", "build", cluster_dir],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        print(f"kustomize build failed: {build.stderr}", file=sys.stderr)
        sys.exit(1)

    apply = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        print(f"oc apply failed: {apply.stderr}", file=sys.stderr)
        sys.exit(1)

    print("Cluster resources applied")
