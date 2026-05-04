"""Poll for the Crossplane-generated aws-credentials-raw Secret.

CLI: fleet-wait-for-aws-creds --cluster-name NAME [--timeout-seconds 900]
Polls every 10s until Secret aws-credentials-raw exists in namespace {cluster}. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--timeout-seconds", default=None)
    args = parser.parse_args()

    check_configmap_env()
    configure("wait-for-aws-creds")

    cluster = resolve_required(args.cluster_name, "cluster-name", "wait-for-aws-creds")
    timeout_str = (
        resolve(args.timeout_seconds, "timeout-seconds", "wait-for-aws-creds") or "900"
    )
    timeout = int(timeout_str)
    info("=== Waiting for aws-credentials-raw Secret ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={timeout}s")
    info(f"  interval=10s")

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
