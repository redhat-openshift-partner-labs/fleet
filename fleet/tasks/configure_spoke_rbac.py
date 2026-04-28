"""Configure RBAC on the spoke cluster.

CLI: fleet-configure-spoke-rbac --cluster-name NAME --spoke-kubeconfig PATH
Creates cluster-admins group and ClusterRoleBinding on spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    configure("configure-spoke-rbac")

    info("=== Configuring spoke RBAC ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    rbac_yaml = textwrap.dedent("""\
        apiVersion: user.openshift.io/v1
        kind: Group
        metadata:
          name: cluster-admins
        users: []
        ---
        apiVersion: rbac.authorization.k8s.io/v1
        kind: ClusterRoleBinding
        metadata:
          name: cluster-admins-binding
        roleRef:
          apiGroup: rbac.authorization.k8s.io
          kind: ClusterRole
          name: cluster-admin
        subjects:
        - apiGroup: rbac.authorization.k8s.io
          kind: Group
          name: cluster-admins
    """)
    info("Applying cluster-admins group and ClusterRoleBinding...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=rbac_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to configure RBAC: {result.stderr}")
        sys.exit(1)
    info("  -> RBAC configured")
