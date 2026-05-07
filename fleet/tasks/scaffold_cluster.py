"""Scaffold a new cluster overlay directory.

CLI: fleet-scaffold-cluster --name NAME --region REGION --tier TIER [options]
Generates clusters/<name>/ with all Kustomize patches pre-populated.
Validates output with kustomize build. Exits 1 on validation failure.
"""

import argparse
import subprocess
import sys

from fleet.scaffold import ClusterParams, write_cluster_dir
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new cluster overlay")
    parser.add_argument("--name", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--tier", required=True, choices=["base", "virt", "ai"])
    parser.add_argument("--environment", default="development")
    parser.add_argument("--control-plane-type", default="m7i.4xlarge")
    parser.add_argument("--worker-type", default="m7i.2xlarge")
    parser.add_argument("--control-plane-replicas", type=int, default=3)
    parser.add_argument("--worker-replicas", type=int, default=3)
    parser.add_argument("--image-set", default="img4.21.13-x86-64-appsub")
    parser.add_argument("--zones", default=None, help="Comma-separated AZ list")
    parser.add_argument(
        "--base-path", default="clusters", help="Parent directory for cluster overlays"
    )
    args = parser.parse_args()

    configure("scaffold-cluster")

    zones = args.zones.split(",") if args.zones else None

    params = ClusterParams(
        name=args.name,
        region=args.region,
        tier=args.tier,
        environment=args.environment,
        control_plane_type=args.control_plane_type,
        worker_type=args.worker_type,
        control_plane_replicas=args.control_plane_replicas,
        worker_replicas=args.worker_replicas,
        image_set=args.image_set,
        zones=zones,
    )

    info(f"Scaffolding cluster '{params.name}' in {args.base_path}/")
    cluster_dir = write_cluster_dir(args.base_path, params)
    info(f"  -> wrote {cluster_dir}")

    info("Validating with kustomize build...")
    for subdir in ["hive", "crossplane"]:
        path = f"{cluster_dir}/{subdir}"
        result = subprocess.run(
            ["kustomize", "build", path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error(f"kustomize build {path} failed: {result.stderr}")
            sys.exit(1)
        info(f"  -> {subdir}: OK")

    info(f"Cluster '{params.name}' scaffolded successfully")
