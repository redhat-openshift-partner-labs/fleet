"""Apply base workloads to the spoke cluster.

CLI: fleet-apply-base-workloads --cluster-name NAME --source-dir DIR --spoke-kubeconfig PATH
Runs kustomize build on source-dir and applies output to spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._env import check_configmap_env, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--source-dir", default=None)
    parser.add_argument("--spoke-kubeconfig", default=None)
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "apply-base-workloads"
    )
    args.source_dir = resolve_required(
        args.source_dir, "source-dir", "apply-base-workloads"
    )
    args.spoke_kubeconfig = resolve_required(
        args.spoke_kubeconfig, "spoke-kubeconfig", "apply-base-workloads"
    )

    cluster = args.cluster_name

    configure("apply-base-workloads")

    info("=== Applying base workloads to spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={args.source_dir}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    info(f"Running kustomize build on {args.source_dir}...")
    build = subprocess.run(
        ["kustomize", "build", args.source_dir],
        capture_output=True,
        text=True,
    )
    info(f"  -> kustomize build exit code: {build.returncode}")
    if build.returncode != 0:
        error(f"kustomize build stderr: {build.stderr}")
        sys.exit(1)
    doc_count = len([l for l in build.stdout.split("---") if l.strip()])
    info(f"  -> kustomize produced {doc_count} YAML documents")

    info(f"Applying workloads to spoke (kubeconfig: {args.spoke_kubeconfig})...")
    apply = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"oc apply stderr: {apply.stderr}")
        sys.exit(1)
    info(f"  -> Apply output: {apply.stdout.strip()}")
    info("Base workloads applied")
