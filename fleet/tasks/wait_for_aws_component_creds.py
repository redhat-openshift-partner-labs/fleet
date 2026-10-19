"""Poll for the Crossplane-generated per-operator AWS credential Secrets (scoped clusters).

CLI: fleet-wait-for-aws-component-creds --cluster-name NAME [--timeout-seconds 600]
Polls every 10s until every <cluster>-<operator>-credentials-raw Secret exists in namespace
{cluster}. On timeout, logs the missing Secrets and their AccessKey status, then exits 1.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._aws_components import COMPONENTS, access_key_name, raw_secret_name
from fleet.tasks._log import configure, error, info


def _report_missing(cluster: str, secrets: list[str]) -> None:
    result = subprocess.run(
        ["oc", "get", "secret", *secrets, "-n", cluster, "-o", "name"],
        capture_output=True,
        text=True,
    )
    present = {line.split("/", 1)[-1] for line in result.stdout.split()}
    missing = [s for s in secrets if s not in present]
    error(f"Missing Secrets in ns '{cluster}': {', '.join(missing)}")

    keys = [access_key_name(cluster, c.key) for c in COMPONENTS]
    diag = subprocess.run(
        [
            "oc",
            "get",
            "accesskey.iam.aws.upbound.io",
            *keys,
            "-o",
            "custom-columns=NAME:.metadata.name,"
            'READY:.status.conditions[?(@.type=="Ready")].status,'
            'SYNCED:.status.conditions[?(@.type=="Synced")].message',
        ],
        capture_output=True,
        text=True,
    )
    info(f"AccessKey status:\n{diag.stdout}{diag.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    configure("wait-for-aws-component-creds")

    cluster = args.cluster_name
    secrets = [raw_secret_name(cluster, c.key) for c in COMPONENTS]
    info("=== Waiting for per-operator AWS credential Secrets ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={args.timeout_seconds}s")
    info(f"  secrets={len(secrets)}")

    timeout = args.timeout_seconds
    elapsed = 0
    interval = 10

    while elapsed < timeout:
        # A single get fails until every named Secret exists
        result = subprocess.run(
            ["oc", "get", "secret", *secrets, "-n", cluster, "-o", "name"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(f"All {len(secrets)} Secrets found (elapsed: {elapsed}s)")
            return

        time.sleep(interval)
        elapsed += interval
        info(f"  Poll [{elapsed}s/{timeout}s]: not ready yet")

    error(f"Timed out after {timeout}s waiting for operator credentials")
    _report_missing(cluster, secrets)
    sys.exit(1)
