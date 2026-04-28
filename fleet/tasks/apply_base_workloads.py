"""Apply base workloads to the spoke cluster.

CLI: fleet-apply-base-workloads --cluster-name NAME --source-dir DIR --spoke-kubeconfig PATH
Runs kustomize build on source-dir and applies output to spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("apply-base-workloads")
    info(f"Applying base workloads for {cluster}...")

    build = subprocess.run(
        ["kustomize", "build", args.source_dir],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        error(f"kustomize build failed: {build.stderr}")
        sys.exit(1)

    apply = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        error(f"Failed to apply workloads: {apply.stderr}")
        sys.exit(1)

    info(f"Applied base workloads for {cluster} on spoke cluster")
