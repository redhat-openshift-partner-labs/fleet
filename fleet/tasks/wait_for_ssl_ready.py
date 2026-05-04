"""Wait for the SSL certificate to be ready.

CLI: fleet-wait-for-ssl-ready --cluster-name NAME [--timeout 15m]
Runs oc wait certificate/{cluster}-tls --for=condition=Ready. Exits 1 on timeout.
"""

import argparse
import subprocess
import sys

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--timeout", default=None)
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "wait-for-ssl-ready"
    )
    args.timeout = resolve(args.timeout, "timeout", "wait-for-ssl-ready") or "15m"

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
            f"certificate/{args.cluster_name}-wildcard-certificate",
            "-n",
            "openshift-ingress",
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
