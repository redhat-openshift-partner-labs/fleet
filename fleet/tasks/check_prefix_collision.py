"""Reject a cluster whose AWS infra prefix collides with any existing cluster.

CLI: fleet-check-prefix-collision --cluster-name NAME --workspace-dir DIR
Scans fleet-clusters directories, hub ClusterDeployments/ManagedClusters, and
Crossplane IAM resource labels for any other cluster that shares the same infra
prefix. Exits 1 if a collision is found, before any resources are created.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from fleet.tasks._aws_components import CLUSTER_LABEL, _IAM_RESOURCES
from fleet.tasks._infra_prefix import infra_prefix
from fleet.tasks._log import configure, error, info


def _fleet_clusters_names(
    workspace: Path,
) -> tuple[dict[str, str], frozenset[str]]:
    names: dict[str, str] = {}
    archive_derived: set[str] = set()
    for subdir in ("provision", "deprovision"):
        parent = workspace / subdir
        if not parent.is_dir():
            continue
        for entry in sorted(parent.iterdir()):
            if entry.is_dir():
                raw = entry.name
                name = raw.removesuffix("-archive")
                if name != raw:
                    archive_derived.add(name)
                names.setdefault(name, f"fleet-clusters {subdir}/{raw}")
    return names, frozenset(archive_derived)


def _hub_cluster_names() -> dict[str, str]:
    names: dict[str, str] = {}
    result = subprocess.run(
        [
            "oc",
            "get",
            "clusterdeployments.hive.openshift.io",
            "--all-namespaces",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for item in json.loads(result.stdout).get("items", []):
            name = item["metadata"]["name"]
            names.setdefault(name, "ClusterDeployment")

    result = subprocess.run(
        [
            "oc",
            "get",
            "managedclusters.cluster.open-cluster-management.io",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for item in json.loads(result.stdout).get("items", []):
            name = item["metadata"]["name"]
            names.setdefault(name, "ManagedCluster")

    return names


def _crossplane_cluster_names() -> dict[str, str]:
    result = subprocess.run(
        ["oc", "get", _IAM_RESOURCES, "-l", CLUSTER_LABEL, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    names: dict[str, str] = {}
    for item in json.loads(result.stdout).get("items", []):
        val = item.get("metadata", {}).get("labels", {}).get(CLUSTER_LABEL)
        if val:
            names.setdefault(val, "Crossplane IAM label")
    return names


def _find_collisions(
    cluster: str,
    all_names: dict[str, str],
    archive_names: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    target = infra_prefix(cluster)
    collisions = []
    for name, source in all_names.items():
        if name == cluster and name not in archive_names:
            continue
        if infra_prefix(name) == target:
            collisions.append((name, source))
    return collisions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--workspace-dir", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    workspace = Path(args.workspace_dir)
    configure("check-prefix-collision")

    info("=== Checking infra prefix collision ===")
    info(f"  cluster-name={cluster}")
    info(f"  prefix={infra_prefix(cluster)}")

    fc_names, archive_names = _fleet_clusters_names(workspace)
    all_names: dict[str, str] = {}
    for k, v in fc_names.items():
        all_names.setdefault(k, v)
    for k, v in _hub_cluster_names().items():
        all_names.setdefault(k, v)
    for k, v in _crossplane_cluster_names().items():
        all_names.setdefault(k, v)

    collisions = _find_collisions(cluster, all_names, archive_names)
    if collisions:
        prefix = infra_prefix(cluster)
        error(f"Infra prefix collision detected for cluster '{cluster}'!")
        error(f"  Shared prefix: {prefix}")
        error(f"  Collisions:")
        for name, source in collisions:
            error(f"    - {name} (source: {source})")
        error(
            "A cluster with a colliding prefix could access this cluster's AWS resources."
        )
        error("Choose a name that produces a unique 21-character infra prefix.")
        sys.exit(1)

    info("No prefix collision found")
