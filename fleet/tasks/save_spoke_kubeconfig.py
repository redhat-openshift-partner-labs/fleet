"""Save the spoke kubeconfig to a Hub Secret for post-provision use.

CLI: fleet-save-spoke-kubeconfig --cluster-name NAME --kubeconfig-file PATH
Reads kubeconfig file and creates Hub Secret {cluster}-spoke-kubeconfig. Exits 1 on failure.
"""

import argparse
import base64
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--kubeconfig-file", required=True)
    parser.add_argument("--namespace", default="openshift-pipelines")
    args = parser.parse_args()

    configure("save-spoke-kubeconfig")
    info(f"Saving spoke kubeconfig for {args.cluster_name}...")

    try:
        with open(args.kubeconfig_file, encoding="utf-8") as f:
            kubeconfig_data = f.read()
    except FileNotFoundError:
        error(f"Kubeconfig file not found: {args.kubeconfig_file}")
        sys.exit(1)

    encoded = base64.b64encode(kubeconfig_data.encode()).decode()

    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {args.cluster_name}-spoke-kubeconfig
          namespace: {args.namespace}
        type: Opaque
        data:
          kubeconfig: {encoded}
    """)

    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to save kubeconfig: {result.stderr}")
        sys.exit(1)

    info(f"Saved spoke kubeconfig to hub Secret for {args.cluster_name}")
