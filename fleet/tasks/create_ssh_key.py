"""Generate an ed25519 SSH key pair and store private key as a Secret.

CLI: fleet-create-ssh-key --cluster-name NAME
Generates a fresh ed25519 key pair via ssh-keygen. Stores the private key
in Secret {cluster}-ssh-key with key=ssh-privatekey (Hive-compatible).
Idempotent via dry-run + apply. Exits 1 on failure.
"""

import argparse
import os
import subprocess
import sys
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    secret_name = f"{cluster}-ssh-key"

    result = subprocess.run(
        ["oc", "get", "secret", secret_name, "-n", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"Secret {secret_name} already exists in {cluster}")
        return

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "key")
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"],
                capture_output=True,
                text=True,
                check=True,
            )
            with open(key_path, encoding="utf-8") as fh:
                private_key = fh.read()

            dry_run = subprocess.run(
                [
                    "oc",
                    "create",
                    "secret",
                    "generic",
                    secret_name,
                    "-n",
                    cluster,
                    f"--from-literal=ssh-privatekey={private_key}",
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
        print(
            f"ERROR: Failed to create {secret_name} in {cluster}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Secret {secret_name} created in {cluster}")
