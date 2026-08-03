"""Finalize spoke cluster for handoff.

CLI: fleet-finalize-spoke --cluster-name NAME --spoke-kubeconfig PATH
Deletes leftover installer pods and the kubeadmin secret. All operations
are best-effort; failures are logged as warnings.
"""

import argparse
import subprocess

from fleet.tasks._log import configure, info, warn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    configure("finalize-spoke")

    info("=== Finalizing spoke cluster ===")
    info("Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    kc = f"--kubeconfig={args.spoke_kubeconfig}"

    info("Deleting installer pods...")
    result = subprocess.run(
        [
            "oc",
            "delete",
            "pods",
            "-A",
            "-l",
            "app=installer",
            "--field-selector=status.phase=Failed",
            "--ignore-not-found=true",
            kc,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"Failed to delete installer pods: {result.stderr}")
    else:
        info("  -> installer pods deleted")

    info("Deleting kubeadmin secret...")
    result = subprocess.run(
        [
            "oc",
            "delete",
            "secret",
            "kubeadmin",
            "-n",
            "kube-system",
            "--ignore-not-found=true",
            kc,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"Failed to delete kubeadmin secret: {result.stderr}")
    else:
        info("  -> kubeadmin secret deleted")

    info("Spoke finalization complete")
