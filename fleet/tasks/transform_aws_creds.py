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

        access_key = base64.b64decode(access_key_b64).decode()
        secret_key = base64.b64decode(secret_key_b64).decode()
    except (subprocess.CalledProcessError, binascii.Error) as exc:
        error(f"Failed to extract aws-credentials-raw in {cluster}: {exc}")
        sys.exit(1)

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
                f"--from-literal=aws_access_key_id={access_key}",
                f"--from-literal=aws_secret_access_key={secret_key}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=dry_run.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(f"Failed to create aws-credentials in {cluster}: {exc}")
        sys.exit(1)

    info(f"aws-credentials Secret created in {cluster}")
