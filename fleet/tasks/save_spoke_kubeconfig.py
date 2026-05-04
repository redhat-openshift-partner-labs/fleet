"""Save the spoke kubeconfig to a Hub Secret for post-provision use.

CLI: fleet-save-spoke-kubeconfig --cluster-name NAME --kubeconfig-file PATH
Reads kubeconfig file and creates Hub Secret {cluster}-spoke-kubeconfig. Exits 1 on failure.
"""

import argparse
import base64
import subprocess
import sys
import textwrap

from fleet.tasks._env import check_configmap_env, resolve, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--kubeconfig-file", default=None)
    parser.add_argument("--namespace", default=None)
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "save-spoke-kubeconfig"
    )
    args.kubeconfig_file = resolve_required(
        args.kubeconfig_file, "kubeconfig-file", "save-spoke-kubeconfig"
    )
    args.namespace = (
        resolve(args.namespace, "namespace", "save-spoke-kubeconfig")
        or "openshift-pipelines"
    )
    configure("save-spoke-kubeconfig")

    info("=== Saving spoke kubeconfig to Hub Secret ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  kubeconfig-file={args.kubeconfig_file}")
    info(f"  namespace={args.namespace}")

    kubeconfig_data = ""
    try:
        with open(args.kubeconfig_file, encoding="utf-8") as f:
            kubeconfig_data = f.read()
    except FileNotFoundError:
        error(f"Kubeconfig file not found: {args.kubeconfig_file}")
        sys.exit(1)

    info(f"  -> Read kubeconfig file (bytes: {len(kubeconfig_data)})")

    encoded = base64.b64encode(kubeconfig_data.encode()).decode()
    info(f"  -> Base64 encoded (bytes: {len(encoded)})")

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
    info(
        f"Applying Secret '{args.cluster_name}-spoke-kubeconfig' in ns '{args.namespace}'..."
    )
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to save kubeconfig: {result.stderr}")
        sys.exit(1)
    info(f"Kubeconfig saved to Secret '{args.cluster_name}-spoke-kubeconfig'")
