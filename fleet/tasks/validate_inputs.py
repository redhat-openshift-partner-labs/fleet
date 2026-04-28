"""Validate that required Secrets exist before provisioning.

CLI: fleet-validate-inputs --cluster-name NAME
Checks: aws-credentials, pull-secret, {cluster}-ssh-key,
{cluster}-install-config in namespace {cluster}.
Exits 1 if any Secret is missing.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info, warn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("validate-inputs")

    errors = 0

    info(f"Validating inputs for cluster {cluster}...")

    required_secrets = [
        "aws-credentials",
        "pull-secret",
        f"{cluster}-ssh-key",
        f"{cluster}-install-config",
    ]

    for secret in required_secrets:
        result = subprocess.run(
            ["oc", "get", "secret", secret, "-n", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(f"  OK Secret {secret} exists")
        else:
            warn(f"  MISSING Secret {secret}")
            errors += 1

    if errors > 0:
        error(f"{errors} required secrets missing")
        sys.exit(1)

    info("All inputs validated")
