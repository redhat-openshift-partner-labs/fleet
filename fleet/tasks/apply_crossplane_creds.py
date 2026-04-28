"""Apply Crossplane IAM resources for a cluster via kustomize build + oc apply.

CLI: fleet-apply-crossplane-creds --cluster-name NAME --source-dir DIR
Builds clusters/{cluster}/ with kustomize and applies the output. Exits 1 on build or apply failure.
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

    crossplane_dir = os.path.join(source, "crossplane")
    configure("apply-crossplane-creds")

    info("=== Applying Crossplane IAM resources ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={source}")
    info(f"  crossplane-dir={crossplane_dir}")

    info(f"Running kustomize build on {crossplane_dir}...")
    build = subprocess.run(
        ["kustomize", "build", crossplane_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)
    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} YAML documents")

    info("Applying Crossplane resources...")
    apply = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")
    info("Crossplane IAM resources applied")
