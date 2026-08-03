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

from fleet.tasks._log import configure, error, info


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

    info(f"  -> loaded {len(metadata)} key(s)")
    print(json.dumps(metadata))
