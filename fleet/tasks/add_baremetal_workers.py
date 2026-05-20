"""Add baremetal workers to existing cluster via MachinePool creation on hub.

CLI: fleet-add-baremetal-workers --cluster-name NAME --pipeline-image IMAGE
Creates additional baremetal worker MachinePool for virtualization workloads.
Exits 1 on failure.
"""

import argparse
import json
import sys
import tempfile
import time
from typing import Any, Dict, Optional

import yaml

from fleet._retry import run_with_retry
from fleet.tasks._log import configure, error, info


def get_cluster_region_and_zones(cluster_name: str) -> Optional[Dict[str, Any]]:
    """Get the AWS region and availability zones from existing ClusterDeployment."""
    info(f"Getting region and zones for cluster {cluster_name}")

    result = run_with_retry(
        [
            "oc",
            "get",
            "clusterdeployment",
            cluster_name,
            "-n",
            cluster_name,
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error(f"Failed to get ClusterDeployment: {result.stderr}")
        return None

    try:
        cd_data = json.loads(result.stdout)
        platform = cd_data["spec"]["platform"]["aws"]
        region = platform["region"]

        # Get zones from existing machinepool-worker (use Hive API)
        mp_result = run_with_retry(
            [
                "oc",
                "get",
                "machinepool.hive.openshift.io",
                f"{cluster_name}-worker",
                "-n",
                cluster_name,
                "-o",
                "json",
                "--ignore-not-found",
            ],
            capture_output=True,
            text=True,
        )

        zones = ["a", "b", "c"]  # Default fallback
        if mp_result.returncode == 0:
            try:
                mp_data = json.loads(mp_result.stdout)
                aws_zones = mp_data["spec"]["platform"]["aws"].get("zones", [])
                if aws_zones:
                    # Extract zone suffixes from full zone names (e.g., "us-east-2a" -> "a")
                    zones = [zone[-1] for zone in aws_zones]
                    info(f"  -> Found existing zones: {aws_zones}")
            except (json.JSONDecodeError, KeyError):
                info("  -> Could not parse existing MachinePool zones, using defaults")

        # Construct full zone names
        full_zones = [f"{region}{suffix}" for suffix in zones]

        info(f"  -> Region: {region}")
        info(f"  -> Zones: {full_zones}")

        return {"region": region, "zones": full_zones}

    except (json.JSONDecodeError, KeyError) as e:
        error(f"Failed to parse ClusterDeployment JSON: {e}")
        return None


def create_baremetal_machinepool(
    cluster_name: str, region_info: Dict[str, Any]
) -> bool:
    """Create a new MachinePool for baremetal workers."""
    mp_name = f"{cluster_name}-baremetal"
    info(f"Creating baremetal MachinePool: {mp_name}")

    machinepool_spec = {
        "apiVersion": "hive.openshift.io/v1",
        "kind": "MachinePool",
        "metadata": {
            "name": mp_name,
            "namespace": cluster_name,
            "labels": {"cluster": cluster_name, "tier": "virt"},
        },
        "spec": {
            "clusterDeploymentRef": {"name": cluster_name},
            "name": "baremetal",
            "platform": {
                "aws": {
                    "rootVolume": {
                        "iops": 4000,
                        "size": 256,  # Larger disk for virtualization workloads
                        "type": "gp3",
                    },
                    "type": "c5d.metal",  # Baremetal instance for hardware virtualization
                    "zones": region_info["zones"],
                }
            },
            "replicas": 1,  # Start with one baremetal worker
            "labels": {
                "node-role.kubernetes.io/worker": "",
                "node-role.kubernetes.io/baremetal": "",
                "fleet.openshift.com/tier": "virt",
            },
        },
    }

    # Write MachinePool to temporary file
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-machinepool.yaml", delete=False, encoding="utf-8"
        ) as f:
            yaml.dump(machinepool_spec, f, default_flow_style=False)
            mp_file = f.name
    except (OSError, yaml.YAMLError) as e:
        error(f"Failed to write MachinePool YAML: {e}")
        return False

    # Apply the MachinePool
    apply_result = run_with_retry(
        ["oc", "apply", "-f", mp_file],
        capture_output=True,
        text=True,
    )

    if apply_result.returncode != 0:
        error(f"Failed to create MachinePool: {apply_result.stderr}")
        return False

    info(f"  -> Created: {apply_result.stdout.strip()}")
    return True


def wait_for_machinepool_ready(cluster_name: str, timeout: int = 2400) -> bool:
    """Wait for the baremetal MachinePool to provision nodes."""
    mp_name = f"{cluster_name}-baremetal"
    info(f"Waiting for MachinePool {mp_name} to be ready (timeout: {timeout}s)")

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Use Hive API explicitly to match what we created
        result = run_with_retry(
            [
                "oc",
                "get",
                "machinepool.hive.openshift.io",
                mp_name,
                "-n",
                cluster_name,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error(f"Failed to get MachinePool status: {result.stderr}")
            time.sleep(30)
            continue

        try:
            mp_data = json.loads(result.stdout)
            status = mp_data.get("status", {})

            # Check replicas vs ready replicas
            replicas = mp_data["spec"]["replicas"]
            running_replicas = status.get("replicas", 0)

            # Sum ready replicas from all MachineSets
            ready_replicas = 0
            machine_sets = status.get("machineSets", [])
            for ms in machine_sets:
                ready_replicas += ms.get("readyReplicas", 0)

            info(
                f"  -> Replicas: {running_replicas}/{replicas}, Ready: {ready_replicas}/{replicas}"
            )

            # Check if all replicas are ready
            if ready_replicas >= replicas and running_replicas >= replicas:
                info(f"  -> MachinePool {mp_name} is ready")
                return True

            # Check for any error conditions
            conditions = status.get("conditions", [])
            for condition in conditions:
                if (
                    condition.get("type") == "Failed"
                    and condition.get("status") == "True"
                ):
                    error(
                        f"MachinePool failed: {condition.get('message', 'Unknown error')}"
                    )
                    return False

        except (json.JSONDecodeError, KeyError) as e:
            error(f"Failed to parse MachinePool status: {e}")

        time.sleep(30)

    error(f"Timeout waiting for MachinePool {mp_name} to be ready")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--pipeline-image", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("add-baremetal-workers")

    info("=== Adding baremetal workers to cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  pipeline-image={args.pipeline_image}")

    # Get cluster region and availability zones
    region_info = get_cluster_region_and_zones(cluster)
    if not region_info:
        sys.exit(1)

    # Create baremetal MachinePool
    if not create_baremetal_machinepool(cluster, region_info):
        sys.exit(1)

    # Wait for MachinePool to be ready
    if not wait_for_machinepool_ready(cluster):
        sys.exit(1)

    info("Baremetal workers successfully added to cluster")
