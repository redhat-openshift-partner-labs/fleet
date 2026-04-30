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

    info("=== Cleaning up hub-side artifacts ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")

    info(
        f"Deleting Certificate {cluster}-wildcard-certificate from openshift-ingress..."
    )
    subprocess.run(
        [
            "oc",
            "delete",
            "certificate",
            f"{cluster}-wildcard-certificate",
            "-n",
            "openshift-ingress",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info("  -> Certificate deleted")

    info(f"Deleting ClusterIssuer letsencrypt-{cluster}...")
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
    info(f"  -> ClusterIssuer letsencrypt-{cluster} deleted")

    info(f"Deleting Secret {cluster}-cert-manager-aws from cert-manager...")
    subprocess.run(
        [
            "oc",
            "delete",
            "secret",
            f"{cluster}-cert-manager-aws",
            "-n",
            "cert-manager",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> Secret {cluster}-cert-manager-aws deleted")

    iam_resources = [
        "user.iam",
        "policy.iam",
        "userpolicyattachment.iam",
        "accesskey.iam",
    ]
    for resource in iam_resources:
        info(f"Deleting {resource} resources...")
        result = subprocess.run(
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
        info(f"  -> {resource}: exit code {result.returncode}")
    info("  -> Crossplane IAM resources deleted")

    info("Waiting 15s for Crossplane resources to be fully cleaned up...")
    time.sleep(15)

    info(f"Deleting namespace {cluster}...")
    result = subprocess.run(
        ["oc", "delete", "namespace", cluster, "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    info(f"  -> Namespace delete exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to delete namespace {cluster}: {result.stderr}")
        sys.exit(1)
    info(f"Namespace {cluster} deleted")
    info("Hub artifacts cleaned up")
