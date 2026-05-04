"""Extract leaf certificate material from the hub cert secret.

CLI: fleet-extract-cert-material --cluster-name NAME [--namespace openshift-pipelines]
Reads tls.crt/tls.key from {cluster}-wildcard-certificate, creates {cluster}-leaf-cert secret. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys
import textwrap

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--namespace", default=None)
    args = parser.parse_args()

    check_configmap_env()
    cluster = resolve_required(
        args.cluster_name, "cluster-name", "extract-cert-material"
    )
    args.namespace = (
        resolve(args.namespace, "namespace", "extract-cert-material")
        or "openshift-ingress"
    )
    configure("extract-cert-material")

    info("=== Extracting leaf certificate material ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  namespace={args.namespace}")

    info(
        f"Getting secret '{cluster}-wildcard-certificate' from ns '{args.namespace}'..."
    )
    get_result = subprocess.run(
        [
            "oc",
            "get",
            f"secret/{cluster}-wildcard-certificate",
            "-n",
            args.namespace,
            "-o",
            "jsonpath={.data}",
        ],
        capture_output=True,
        text=True,
    )
    if get_result.returncode != 0:
        error(f"Failed to get cert secret: {get_result.stderr}")
        sys.exit(1)
    info(f"  -> Secret data bytes: {len(get_result.stdout)}")

    data = json.loads(get_result.stdout)
    tls_crt = data["tls.crt"]
    tls_key = data["tls.key"]
    info(f"  -> tls.crt length: {len(tls_crt)} bytes")
    info(f"  -> tls.key length: {len(tls_key)} bytes")

    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {cluster}-leaf-cert
          namespace: {args.namespace}
        type: kubernetes.io/tls
        data:
          tls.crt: {tls_crt}
          tls.key: {tls_key}
    """)
    info(f"Creating leaf-cert secret in ns {args.namespace}...")
    apply_result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply_result.returncode}")
    if apply_result.returncode != 0:
        error(f"Failed to create leaf-cert secret: {apply_result.stderr}")
        sys.exit(1)
    info("Leaf certificate material extracted and saved")
