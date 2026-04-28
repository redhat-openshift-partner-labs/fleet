"""Poll for the Crossplane-generated aws-credentials-raw Secret.

CLI: fleet-wait-for-aws-creds --cluster-name NAME [--timeout-seconds 600]
Polls every 10s until Secret aws-credentials-raw exists in namespace {cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("wait-for-aws-creds")

    timeout = args.timeout_seconds
    elapsed = 0
    interval = 10

    info(f"Waiting for aws-credentials-raw Secret in namespace {cluster}...")

    while elapsed < timeout:
        result = subprocess.run(
            ["oc", "get", "secret", "aws-credentials-raw", "-n", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(f"aws-credentials-raw Secret found in {cluster}")
            return

        time.sleep(interval)
        elapsed += interval
        info(f"  Waiting... ({elapsed}s / {timeout}s)")

    error(f"Timed out after {timeout}s waiting for aws-credentials-raw")
    subprocess.run(
        ["oc", "get", "user.iam,accesskey.iam,job", "-n", cluster],
        capture_output=True,
        text=True,
    )
    sys.exit(1)
