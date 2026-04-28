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
    info(f"Building kustomize output for {crossplane_dir}...")
    build = subprocess.run(
        ["kustomize", "build", crossplane_dir],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        error(f"kustomize build failed: {build.stderr}")
        sys.exit(1)

    info(f"Applying Crossplane resources for {cluster}...")
    apply = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        error(f"oc apply failed: {apply.stderr}")
        sys.exit(1)

    info(f"Crossplane resources applied for {cluster}")
