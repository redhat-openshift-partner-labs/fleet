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

    configure("wait-for-aws-creds")

    cluster = args.cluster_name
    info("=== Waiting for aws-credentials-raw Secret ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={args.timeout_seconds}s")
    info(f"  interval=10s")

    timeout = args.timeout_seconds
    elapsed = 0
    interval = 10

    info(f"Polling for secret 'aws-credentials-raw' in ns '{cluster}'...")

    while elapsed < timeout:
        result = subprocess.run(
            ["oc", "get", "secret", "aws-credentials-raw", "-n", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(
                f"Secret 'aws-credentials-raw' found in ns '{cluster}' (elapsed: {elapsed}s)"
            )
            return

        time.sleep(interval)
        elapsed += interval
        info(f"  Poll [{elapsed}s/{timeout}s]: not ready yet")

    error(
        f"Timed out after {timeout}s waiting for aws-credentials-raw in ns '{cluster}'"
    )
    subprocess.run(
        ["oc", "get", "user.iam,accesskey.iam,job", "-n", cluster],
        capture_output=True,
        text=True,
    )
    sys.exit(1)
