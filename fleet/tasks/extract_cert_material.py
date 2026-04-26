"""Extract leaf certificate material from the hub cert secret.

CLI: fleet-extract-cert-material --cluster-name NAME [--namespace openshift-pipelines]
Reads tls.crt/tls.key from {cluster}-tls, creates {cluster}-leaf-cert secret. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys
import textwrap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--namespace", default="openshift-pipelines")
    args = parser.parse_args()

    cluster = args.cluster_name

    get_result = subprocess.run(
        [
            "oc",
            "get",
            f"secret/{cluster}-tls",
            "-n",
            args.namespace,
            "-o",
            "jsonpath={.data}",
        ],
        capture_output=True,
        text=True,
    )
    if get_result.returncode != 0:
        print(f"Failed to get cert secret: {get_result.stderr}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(get_result.stdout)
    tls_crt = data["tls.crt"]
    tls_key = data["tls.key"]

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

    apply_result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    if apply_result.returncode != 0:
        print(
            f"Failed to create leaf-cert secret: {apply_result.stderr}", file=sys.stderr
        )
        sys.exit(1)
