"""Validate that required Secrets exist before provisioning.

CLI: fleet-validate-inputs --cluster-name NAME
Checks: aws-credentials, pull-secret, {cluster}-ssh-key,
{cluster}-install-config in namespace {cluster}.
Exits 1 if any Secret is missing.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    errors = 0

    print(f"Validating inputs for cluster {cluster}...")

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
            print(f"  OK Secret {secret} exists")
        else:
            print(f"  MISSING Secret {secret}")
            errors += 1

    if errors > 0:
        print(f"ERROR: {errors} required secrets missing", file=sys.stderr)
        sys.exit(1)

    print("All inputs validated")
