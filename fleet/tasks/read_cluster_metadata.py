"""Read per-cluster metadata from a cluster directory.

CLI: fleet-read-cluster-metadata --cluster-dir PATH
Reads metadata.yaml from the cluster directory and outputs JSON to stdout.
Outputs {} if the file is missing or empty. Exits 1 if the directory does not exist.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from fleet.tasks._schedule import schedule_error, timezone_error
from fleet.tasks._log import configure, error, info

SUPPORTED_AI_ACCELERATORS = {"none", "nvidia-gpu"}
# One EC2 instance type name (family.size); the value is written into the post-provision
# PipelineRun YAML. Which types are valid for the tier is checked by fleet-cluster-scaffold.
PODVM_INSTANCE_TYPE = re.compile(r"[a-z0-9-]+\.[a-z0-9-]+")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-dir", required=True)
    args = parser.parse_args()

    configure("read-cluster-metadata")

    cluster_dir = Path(args.cluster_dir)
    if not cluster_dir.is_dir():
        error(f"Cluster directory does not exist: {cluster_dir}")
        sys.exit(1)

    metadata_path = cluster_dir / "metadata.yaml"
    info(f"Reading metadata from {metadata_path}")

    if not metadata_path.exists():
        info("  -> metadata.yaml not found, returning empty")
        print("{}")
        return

    with open(metadata_path, encoding="utf-8") as f:
        metadata = yaml.safe_load(f) or {}

    if not isinstance(metadata, dict):
        error("metadata.yaml must contain a YAML object")
        sys.exit(1)

    accelerator = metadata.get("ai-accelerator")
    if accelerator is not None and accelerator not in SUPPORTED_AI_ACCELERATORS:
        error(
            "Invalid ai-accelerator value: "
            f"{accelerator}; expected one of {sorted(SUPPORTED_AI_ACCELERATORS)}"
        )
        sys.exit(1)

    timezone = metadata.get("timezone")
    if timezone is not None:
        message = timezone_error(timezone)
        if message:
            error(message)
            sys.exit(1)

    schedule = metadata.get("schedule")
    if schedule is not None:
        message = schedule_error(schedule)
        if message:
            error(message)
            sys.exit(1)

    if "podvm-instance-type" in metadata:
        instance_type = metadata["podvm-instance-type"]
        if not isinstance(instance_type, str) or not PODVM_INSTANCE_TYPE.fullmatch(
            instance_type
        ):
            error(f"Invalid podvm-instance-type value: {instance_type}")
            sys.exit(1)

    info(f"  -> loaded {len(metadata)} key(s)")
    print(json.dumps(metadata))
