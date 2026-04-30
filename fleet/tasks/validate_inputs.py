"""Validate that required Secrets exist before provisioning.

CLI: fleet-validate-inputs --cluster-name NAME
Checks: aws-credentials, pull-secret, {cluster}-ssh-key,
in namespace {cluster}.
Exits 1 if any Secret is missing.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("validate-inputs")

    info("=== Validating required Secrets ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info("Checking required secrets in ns {cluster}...")
    required_secrets = [
        "aws-credentials",
        "pull-secret",
        f"{cluster}-ssh-key",
    ]

    errors = 0
    for secret in required_secrets:
        result = subprocess.run(
            ["oc", "get", "secret", secret, "-n", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(f"  OK Secret '{secret}' exists")
        else:
            error(f"  MISSING Secret '{secret}'")
            errors += 1

    info(f"Validation complete: {errors} missing secrets")
    if errors > 0:
        error(f"{errors} required secrets missing from ns {cluster}")
        sys.exit(1)
    info("All required Secrets present")
