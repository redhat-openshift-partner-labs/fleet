"""Read per-cluster metadata from a cluster directory.

CLI: fleet-read-cluster-metadata --cluster-dir PATH
Reads metadata.yaml from the cluster directory and outputs JSON to stdout.
Outputs {} if the file is missing or empty. Exits 1 if the directory does not exist.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from fleet.tasks._schedule import schedule_error, timezone_error
from fleet.tasks._log import configure, error, info

SUPPORTED_AI_ACCELERATORS = {"none", "nvidia-gpu"}


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

    info(f"  -> loaded {len(metadata)} key(s)")
    print(json.dumps(metadata))
