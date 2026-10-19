"""Apply Hive cluster CRs (ClusterDeployment, MachinePool, ManagedCluster, etc.).

CLI: fleet-apply-cluster-crs --cluster-name NAME --source-dir DIR
Builds the cluster's hive overlay with kustomize and applies via oc. If the ClusterDeployment
references a Hive manifests Secret (spec.provisioning.manifestsSecretRef, scoped AWS clusters), it
must already exist; otherwise nothing is applied, rather than letting Hive start an install that
cannot load its manifests. Exits 1 on build, missing manifests Secret, or apply failure.
"""

import argparse
import os
import subprocess
import sys

import yaml

from fleet._retry import run_with_retry
from fleet.tasks._log import configure, error, info


def _manifests_secret_ref(rendered: str) -> tuple[str, str] | None:
    """(namespace, name) of the ClusterDeployment's manifestsSecretRef, if any."""
    for doc in yaml.safe_load_all(rendered):
        if isinstance(doc, dict) and doc.get("kind") == "ClusterDeployment":
            ref = (doc.get("spec", {}).get("provisioning") or {}).get(
                "manifestsSecretRef"
            )
            if ref:
                return doc["metadata"]["namespace"], ref["name"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

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
    build = run_with_retry(
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

    ref = _manifests_secret_ref(build.stdout)
    if ref:
        namespace, name = ref
        info(f"Checking Hive manifests Secret {namespace}/{name}...")
        check = subprocess.run(
            ["oc", "get", "secret", name, "-n", namespace, "-o", "name"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            error(
                f"ClusterDeployment references manifests Secret {namespace}/{name}, "
                "which does not exist; pre-provision must create it "
                "(build-aws-credentials-manifests). Not applying."
            )
            sys.exit(1)
        info("  -> found")

    info("Applying cluster CRs via oc apply (server-side, force-conflicts)...")
    apply = run_with_retry(
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
