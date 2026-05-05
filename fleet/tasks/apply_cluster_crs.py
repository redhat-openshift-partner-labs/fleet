"""Apply Hive cluster CRs (ClusterDeployment, MachinePool, ManagedCluster, etc.).

CLI: fleet-apply-cluster-crs --cluster-name NAME --source-dir DIR
Builds clusters/{cluster}/ with kustomize and applies via oc. Exits 1 on build or apply failure.
"""

import argparse
import os
import subprocess
import sys

from fleet.tasks._env import check_configmap_env, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--source-dir", default=None)
    args = parser.parse_args()
    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "apply-cluster-crs"
    )
    args.source_dir = resolve_required(
        args.source_dir, "source-dir", "apply-cluster-crs"
    )

    cluster = args.cluster_name
    source = args.source_dir

    hive_dir = os.path.join(source, "hive")
    configure("apply-cluster-crs")

    info("=== Applying cluster CRs ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={source}")
    info(f"  hive-dir={hive_dir}")

    info(f"Running kustomize build on {hive_dir}...")
    build = subprocess.run(
        ["kustomize", "build", hive_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)
    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} YAML documents")

    info("Applying cluster CRs via oc apply (server-side, force-conflicts)...")
    apply = subprocess.run(
        ["oc", "apply", "--server-side=true", "--force-conflicts", "-f", "-"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")
    info("Cluster resources applied")
