"""Transform aws-credentials-raw into aws-credentials for Hive.

CLI: fleet-transform-aws-creds --cluster-name NAME
Reads aws-credentials-raw (username/password), creates aws-credentials
(aws_access_key_id/aws_secret_access_key). Exits 1 on failure.
"""

import argparse
import base64
import binascii
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("transform-aws-creds")

    info("=== Transforming AWS credentials for Hive ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info("Reading aws-credentials-raw secret 'username' (base64) from ns {cluster}...")
    try:
        access_key_b64 = subprocess.run(
            [
                "oc",
                "get",
                "secret",
                "aws-credentials-raw",
                "-n",
                cluster,
                "-o",
                "jsonpath={.data.username}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        info(f"  -> Read username (b64, bytes: {len(access_key_b64)})")

        info(
            "Reading aws-credentials-raw secret 'password' (base64) from ns {cluster}..."
        )
        secret_key_b64 = subprocess.run(
            [
                "oc",
                "get",
                "secret",
                "aws-credentials-raw",
                "-n",
                cluster,
                "-o",
                "jsonpath={.data.password}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        info(f"  -> Read password (b64, bytes: {len(secret_key_b64)})")

        access_key = base64.b64decode(access_key_b64).decode()
        secret_key = base64.b64decode(secret_key_b64).decode()
        info("  -> Base64 decoded")
        info(
            f"  -> aws_access_key_id: {access_key[:8]}... (total {len(access_key)} chars)"
        )
        info(
            f"  -> aws_secret_access_key: {secret_key[:8]}... (total {len(secret_key)} chars)"
        )
    except (subprocess.CalledProcessError, binascii.Error) as exc:
        error(f"Failed to extract aws-credentials-raw: {exc}")
        sys.exit(1)

    info("Creating aws-credentials secret via dry-run...")
    try:
        dry_run = subprocess.run(
            [
                "oc",
                "create",
                "secret",
                "generic",
                "aws-credentials",
                "-n",
                cluster,
                "--from-literal=aws_access_key_id=[REDACTED]",
                "--from-literal=aws_secret_access_key=[REDACTED]",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info("  -> Dry-run YAML generated")

        info("Applying aws-credentials secret...")
        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=dry_run.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(f"Failed to create aws-credentials: {exc}")
        sys.exit(1)

    info("aws-credentials Secret created")
