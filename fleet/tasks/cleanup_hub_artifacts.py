"""Clean up hub-side artifacts after cluster deprovision.

CLI: fleet-cleanup-hub-artifacts --cluster-name NAME
Deletes certificate CRs, ClusterIssuer, Crossplane IAM resources, then namespace.
IAM resources cover both legacy (installer user only) and scoped AWS clusters (per-operator
users and BYO node roles); missing ones are ignored. Deletes and polls use one oc call each.
Non-critical deletions are best-effort. Exits 1 if namespace deletion fails.
"""

import argparse
import json
import subprocess
import sys
import time

from fleet.tasks._aws_components import iam_targets
from fleet.tasks._log import configure, error, info, warn

_POLL_INTERVAL = 2
_POLL_TIMEOUT = 60


def _delete_iam_no_wait(targets: list[str]) -> None:
    info(f"Deleting {len(targets)} IAM resource name(s) (no-wait)...")
    result = subprocess.run(
        ["oc", "delete", *targets, "--wait=false", "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )
    info(f"  -> IAM delete exit code {result.returncode}")


def _wait_iam_deleted(targets: list[str], timeout: int = _POLL_TIMEOUT) -> list[str]:
    """Poll until all targets are gone; return the ones still present (or unknown) at timeout."""
    max_attempts = timeout // _POLL_INTERVAL
    remaining = targets
    for attempt in range(max_attempts):
        result = subprocess.run(
            ["oc", "get", *targets, "--ignore-not-found", "-o", "name"],
            capture_output=True,
            text=True,
        )
        # A failed get proves nothing is gone; keep every target as remaining
        remaining = result.stdout.split() if result.returncode == 0 else targets
        if result.returncode == 0 and not remaining:
            info("  -> All IAM resources deleted")
            return []
        if attempt < max_attempts - 1:
            time.sleep(_POLL_INTERVAL)
    warn(f"{len(remaining)} IAM resource(s) still present after {timeout}s timeout")
    return remaining


def _force_remove_finalizers(remaining: list[str]) -> None:
    patch_payload = json.dumps({"metadata": {"finalizers": None}})
    for name in remaining:
        info(f"Removing finalizers from {name}...")
        result = subprocess.run(
            ["oc", "patch", name, "--type=merge", f"-p={patch_payload}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            warn(f"  -> Failed to patch {name}: {result.stderr}")
        else:
            info(f"  -> {name} finalizers removed")


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

    info("Deleting Crossplane IAM resources...")
    targets = iam_targets(cluster)
    _delete_iam_no_wait(targets)

    info("Waiting for IAM resources to be fully deleted...")
    remaining = _wait_iam_deleted(targets)
    if remaining:
        warn("Some IAM resources still exist, removing Crossplane finalizers...")
        _force_remove_finalizers(remaining)

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
