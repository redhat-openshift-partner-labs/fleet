"""Configure RBAC on the spoke cluster.

CLI: fleet-configure-spoke-rbac --cluster-name NAME --spoke-kubeconfig PATH
Creates cluster-admins group and ClusterRoleBinding on spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--cluster-admins", default="")
    args = parser.parse_args()

    configure("configure-spoke-rbac")

    admins = [u.strip() for u in args.cluster_admins.split(",") if u.strip()]

    info("=== Configuring spoke RBAC ===")
    info("Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")
    info(f"  cluster-admins={admins}")

    if admins:
        users_lines = "users:\n" + "".join(f"  - {u}\n" for u in admins)
    else:
        users_lines = "users: []\n"

    rbac_yaml = (
        "---\n"
        "apiVersion: user.openshift.io/v1\n"
        "kind: Group\n"
        "metadata:\n"
        "  name: cluster-admins\n"
        f"{users_lines}"
        "---\n"
        "apiVersion: rbac.authorization.k8s.io/v1\n"
        "kind: ClusterRoleBinding\n"
        "metadata:\n"
        "  name: cluster-admins-binding\n"
        "roleRef:\n"
        "  apiGroup: rbac.authorization.k8s.io\n"
        "  kind: ClusterRole\n"
        "  name: cluster-admin\n"
        "subjects:\n"
        "- apiGroup: rbac.authorization.k8s.io\n"
        "  kind: Group\n"
        "  name: cluster-admins\n"
    )
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
