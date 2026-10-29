"""Create the recurring hub-side cluster job.

CLI: fleet-create-cluster-cronjob --cluster-name NAME --timezone NAME --schedule CRON
Creates a CronJob in the default namespace using the pre-provisioned ecoeng
service account. Exits 1 if validation, the service account check, or apply fails.
"""

import argparse
import subprocess
import sys
from typing import Any

import yaml

from fleet._retry import run_with_retry
from fleet.tasks._log import configure, error, info
from fleet.tasks._schedule import schedule_error, timezone_error

DEFAULT_NAMESPACE = "default"
SERVICE_ACCOUNT = "ecoeng"


def _cronjob(cluster: str, timezone: str, schedule: str) -> dict[str, Any]:
    return {
        "kind": "CronJob",
        "apiVersion": "batch/v1",
        "metadata": {"name": cluster, "namespace": DEFAULT_NAMESPACE},
        "spec": {
            "schedule": schedule,
            "timeZone": timezone,
            "suspend": False,
            "jobTemplate": {
                "metadata": {},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "handler",
                                    "image": "quay.io/rhopl/osplc:v0.0.2",
                                    "command": [
                                        "/app/osplc",
                                        "start",
                                        "cluster",
                                        "--cluster",
                                        cluster,
                                    ],
                                    "imagePullPolicy": "Always",
                                }
                            ],
                            "restartPolicy": "Never",
                            "serviceAccountName": SERVICE_ACCOUNT,
                            "schedulerName": "default-scheduler",
                        }
                    }
                },
            },
            "successfulJobsHistoryLimit": 3,
            "failedJobsHistoryLimit": 1,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--schedule", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    timezone = args.timezone
    schedule = args.schedule
    configure("create-cluster-cronjob")

    info("=== Creating hub-side cluster CronJob ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timezone={timezone}")
    info(f"  schedule={schedule}")

    timezone_message = timezone_error(timezone)
    if timezone_message:
        error(timezone_message)
        sys.exit(1)

    schedule_message = schedule_error(schedule)
    if schedule_message:
        error(schedule_message)
        sys.exit(1)

    info(f"Checking serviceaccount/{SERVICE_ACCOUNT} in {DEFAULT_NAMESPACE}...")
    service_account = subprocess.run(
        ["oc", "get", "serviceaccount", SERVICE_ACCOUNT, "-n", DEFAULT_NAMESPACE],
        capture_output=True,
        text=True,
    )
    info(f"  -> service account check exit code: {service_account.returncode}")
    if service_account.returncode != 0:
        error(
            f"Failed to find serviceaccount/{SERVICE_ACCOUNT} "
            f"in namespace {DEFAULT_NAMESPACE}: {service_account.stderr}"
        )
        sys.exit(1)

    manifest = yaml.safe_dump(_cronjob(cluster, timezone, schedule), sort_keys=False)
    info(f"Applying CronJob {cluster} to hub namespace {DEFAULT_NAMESPACE}...")
    apply = run_with_retry(
        [
            "oc",
            "apply",
            "--server-side=true",
            "--force-conflicts",
            "-f",
            "-",
        ],
        input=manifest,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply.returncode}")
    if apply.returncode != 0:
        error(f"Failed to apply CronJob: {apply.stderr}")
        sys.exit(1)
    info(f"CronJob {cluster} applied in {DEFAULT_NAMESPACE}")
