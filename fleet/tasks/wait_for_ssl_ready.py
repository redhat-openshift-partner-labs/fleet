"""Wait for the SSL certificate to be ready.

CLI: fleet-wait-for-ssl-ready --cluster-name NAME [--timeout 15m]
Runs oc wait certificate/{cluster}-tls --for=condition=Ready. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="15m")
    args = parser.parse_args()

    configure("wait-for-ssl-ready")

    info("=== Waiting for SSL certificate to be ready ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  timeout={args.timeout}")

    info("Waiting for certificate to be ready (condition: Ready)...")
    result = subprocess.run(
        [
            "oc",
            "wait",
            f"certificate/{args.cluster_name}-tls",
            "--for=condition=Ready",
            f"--timeout={args.timeout}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc wait exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Certificate not ready: {result.stderr}")
        sys.exit(1)
    info("SSL certificate is ready")
