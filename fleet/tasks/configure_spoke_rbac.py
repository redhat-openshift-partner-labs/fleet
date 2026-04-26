"""Configure RBAC on the spoke cluster.

CLI: fleet-configure-spoke-rbac --cluster-name NAME --spoke-kubeconfig PATH
Creates cluster-admins group and ClusterRoleBinding on spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

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

    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=rbac_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to configure RBAC: {result.stderr}", file=sys.stderr)
        sys.exit(1)
