"""Validate that required Secrets exist before provisioning.

CLI: fleet-validate-inputs --cluster-name NAME [--image-set IMAGESET]
Checks: aws-credentials, pull-secret, {cluster}-ssh-key, {cluster}-install-config
in namespace {cluster}. Optionally checks ClusterImageSet existence.
Exits 1 if any resource is missing.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--image-set", default=None)
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
        f"{cluster}-install-config",
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

    if args.image_set:
        info(f"Checking ClusterImageSet '{args.image_set}'...")
        result = subprocess.run(
            ["oc", "get", "clusterimagesets.hive.openshift.io", args.image_set],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            info(f"  OK ClusterImageSet '{args.image_set}' exists")
        else:
            error(f"  MISSING ClusterImageSet '{args.image_set}'")
            errors += 1

    info(f"Validation complete: {errors} missing resources")
    if errors > 0:
        error(f"{errors} required resources missing")
        sys.exit(1)
    info("All required resources present")
