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

from fleet.tasks._env import resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    args = parser.parse_args()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "create-ssh-key"
    )

    cluster = args.cluster_name
    secret_name = f"{cluster}-ssh-key"
    configure("create-ssh-key")

    info("=== Creating SSH key pair ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  secret-name={secret_name}")

    info(f"Checking if secret '{secret_name}' exists...")
    result = subprocess.run(
        ["oc", "get", "secret", secret_name, "-n", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info(f"Secret {secret_name} already exists")
        return

    info("Generating ed25519 SSH key pair...")
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
                _ = fh.read()

            dry_run = subprocess.run(
                [
                    "oc",
                    "create",
                    "secret",
                    "generic",
                    secret_name,
                    "-n",
                    cluster,
                    "--from-literal=ssh-privatekey=[redacted]",
                    "--dry-run=client",
                    "-o",
                    "yaml",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        _ = subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=dry_run.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(f"Failed to create {secret_name} in {cluster}: {exc}")
        sys.exit(1)

    info(f"Secret '{secret_name}' created in ns {cluster}")
