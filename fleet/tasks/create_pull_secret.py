"""Copy pull-secret from a hub namespace into the cluster namespace.

CLI: fleet-create-pull-secret --cluster-name NAME
       [--source-namespace NS] [--source-secret-name SECRET]
Reads the pull-secret from source (default openshift-config/pull-secret),
rewrites metadata for the target namespace, and applies it.
Idempotent: skips if secret already exists. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--source-namespace", default=None)
    parser.add_argument("--source-secret-name", default=None)
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "create-pull-secret"
    )
    args.source_namespace = (
        resolve(args.source_namespace, "source-namespace", "create-pull-secret")
        or "openshift-config"
    )
    args.source_secret_name = (
        resolve(args.source_secret_name, "source-secret-name", "create-pull-secret")
        or "pull-secret"
    )

    cluster = args.cluster_name
    source_ns = args.source_namespace
    source_name = args.source_secret_name

    configure("create-pull-secret")

    info("=== Creating pull-secret in cluster namespace ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-namespace={source_ns}")
    info(f"  source-secret-name={source_name}")

    info(f"Checking if pull-secret exists in ns {cluster}...")
    result = subprocess.run(
        ["oc", "get", "secret", "pull-secret", "-n", cluster],
        capture_output=True,
        text=True,
    )
    info(f"  -> exit code: {result.returncode}")
    if result.returncode == 0:
        info("Secret pull-secret already exists in {cluster}")
        return

    info(f"Reading secret '{source_name}' from ns '{source_ns}'...")
    try:
        result = subprocess.run(
            ["oc", "get", "secret", source_name, "-n", source_ns, "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        info(f"  -> Read pull-secret (bytes: {len(result.stdout)})")

        secret = json.loads(result.stdout)
        old_ns = secret.get("metadata", {}).get("namespace", "unknown")
        info(f"Rewriting secret metadata: ns={old_ns} -> {cluster}")
        secret["metadata"] = {"name": "pull-secret", "namespace": cluster}
        secret.pop("status", None)

        info(f"Applying pull-secret to cluster ns {cluster}...")
        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=json.dumps(secret),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(
            f"Failed to copy pull-secret from {source_ns}/{source_name} to {cluster}: {exc}"
        )
        sys.exit(1)

    info(f"Secret pull-secret created in ns {cluster}")
