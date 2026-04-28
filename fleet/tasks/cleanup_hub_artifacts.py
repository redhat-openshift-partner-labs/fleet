"""Clean up hub-side artifacts after cluster deprovision.

CLI: fleet-cleanup-hub-artifacts --cluster-name NAME
Deletes certificate CRs, ClusterIssuer, Crossplane IAM resources, then namespace.
Non-critical deletions are best-effort. Exits 1 if namespace deletion fails.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("cleanup-hub-artifacts")
    info(f"Cleaning up hub-side artifacts for {cluster}...")

    subprocess.run(
        [
            "oc",
            "delete",
            "certificate",
            "-n",
            cluster,
            "--all",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  Certificate CRs deleted")

    subprocess.run(
        [
            "oc",
            "delete",
            "clusterissuer",
            f"letsencrypt-{cluster}",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  ClusterIssuer deleted")

    for resource in [
        "user.iam",
        "policy.iam",
        "userpolicyattachment.iam",
        "accesskey.iam",
    ]:
        subprocess.run(
            [
                "oc",
                "delete",
                resource,
                "-n",
                cluster,
                "--all",
                "--ignore-not-found=true",
            ],
            capture_output=True,
            text=True,
        )
    info("  Crossplane IAM resources deleted")

    info("Waiting for Crossplane resources to be fully cleaned up...")
    time.sleep(15)

    result = subprocess.run(
        [
            "oc",
            "delete",
            "namespace",
            cluster,
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to delete namespace {cluster}: {result.stderr}")
        sys.exit(1)
    info(f"  Namespace {cluster} deleted (takes remaining secrets with it)")

    info("Hub artifacts cleaned up")
