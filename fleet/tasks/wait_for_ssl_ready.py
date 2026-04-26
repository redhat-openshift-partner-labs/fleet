"""Wait for the SSL certificate to be ready.

CLI: fleet-wait-for-ssl-ready --cluster-name NAME [--timeout 15m]
Runs oc wait certificate/{cluster}-tls --for=condition=Ready. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="15m")
    args = parser.parse_args()

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
    if result.returncode != 0:
        print(f"Certificate not ready: {result.stderr}", file=sys.stderr)
        sys.exit(1)
