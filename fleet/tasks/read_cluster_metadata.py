"""Read per-cluster metadata from a cluster directory.

CLI: fleet-read-cluster-metadata --cluster-dir PATH
Reads metadata.yaml from the cluster directory and outputs JSON to stdout.
Outputs {} if the file is missing or empty. Exits 1 if the directory does not exist.
"""

import argparse
import re
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from fleet.tasks._log import configure, error, info

SUPPORTED_AI_ACCELERATORS = {"none", "nvidia-gpu"}
CRON_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _validate_timezone(timezone: object) -> None:
    if not isinstance(timezone, str):
        error(f"Invalid timezone value: {timezone}; expected an IANA timezone name")
        sys.exit(1)
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        error(f"Invalid timezone value: {timezone}; expected an IANA timezone name")
        sys.exit(1)


def _validate_schedule(schedule: object) -> None:
    if not isinstance(schedule, str):
        error(
            f"Invalid schedule value: {schedule}; expected a five-field cron expression"
        )
        sys.exit(1)

    fields = schedule.split()
    if len(fields) != len(CRON_FIELD_RANGES):
        error(
            f"Invalid schedule value: {schedule}; "
            "expected a five-field cron expression"
        )
        sys.exit(1)

    for field, (minimum, maximum) in zip(fields, CRON_FIELD_RANGES):
        for part in field.split(","):
            match = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
            if match is None:
                error(
                    f"Invalid schedule value: {schedule}; "
                    f"invalid cron field: {field}"
                )
                sys.exit(1)

            bounds = match.group(1)
            if bounds == "*":
                continue

            numbers = [int(value) for value in bounds.split("-")]
            if any(number < minimum or number > maximum for number in numbers):
                error(
                    f"Invalid schedule value: {schedule}; "
                    f"field {field} is outside {minimum}-{maximum}"
                )
                sys.exit(1)

            step = match.group(2)
            if step is not None and int(step) == 0:
                error(
                    f"Invalid schedule value: {schedule}; "
                    f"field {field} has a zero step"
                )
                sys.exit(1)


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
        _validate_timezone(timezone)

    schedule = metadata.get("schedule")
    if schedule is not None:
        _validate_schedule(schedule)

    info(f"  -> loaded {len(metadata)} key(s)")
    print(json.dumps(metadata))
