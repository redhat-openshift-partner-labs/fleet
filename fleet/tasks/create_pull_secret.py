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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-namespace", default="openshift-config")
    parser.add_argument("--source-secret-name", default="pull-secret")
    args = parser.parse_args()

    cluster = args.cluster_name
    source_ns = args.source_namespace
    source_name = args.source_secret_name

    result = subprocess.run(
        ["oc", "get", "secret", "pull-secret", "-n", cluster],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"Secret pull-secret already exists in {cluster}")
        return

    try:
        result = subprocess.run(
            [
                "oc",
                "get",
                "secret",
                source_name,
                "-n",
                source_ns,
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        secret = json.loads(result.stdout)
        secret["metadata"] = {"name": "pull-secret", "namespace": cluster}
        secret.pop("status", None)

        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=json.dumps(secret),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"ERROR: Failed to copy pull-secret to {cluster}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Secret pull-secret created in {cluster}")
