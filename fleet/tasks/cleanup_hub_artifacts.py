"""Clean up hub-side artifacts after cluster deprovision.

CLI: fleet-cleanup-hub-artifacts --cluster-name NAME
Deletes certificate CRs, ClusterIssuer, Crossplane IAM resources, then namespace.
Non-critical deletions are best-effort. Exits 1 if namespace deletion fails.
"""

import argparse
import json
import subprocess
import sys
import time

from fleet.tasks._log import configure, error, info, warn

_IAM_RESOURCES = {
    "userpolicyattachment.iam": "policy-attachment",
    "policy.iam": "openshift4installerpolicy",
    "accesskey.iam": "access-key",
    "user.iam": "ocp-installer",
}

_POLL_INTERVAL = 2
_POLL_TIMEOUT = 60


def _delete_iam_no_wait(cluster: str) -> None:
    for resource, suffix in _IAM_RESOURCES.items():
        name = f"{cluster}-{suffix}"
        info(f"Deleting {resource} {name} (no-wait)...")
        result = subprocess.run(
            [
                "oc",
                "delete",
                resource,
                name,
                "--wait=false",
                "--ignore-not-found=true",
            ],
            capture_output=True,
            text=True,
        )
        info(f"  -> {resource}: exit code {result.returncode}")


def _wait_iam_deleted(cluster: str, timeout: int = _POLL_TIMEOUT) -> bool:
    max_attempts = timeout // _POLL_INTERVAL
    for attempt in range(max_attempts):
        all_gone = True
        for resource, suffix in _IAM_RESOURCES.items():
            name = f"{cluster}-{suffix}"
            result = subprocess.run(
                ["oc", "get", resource, name],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                continue
            all_gone = False
        if all_gone:
            info("  -> All IAM resources deleted")
            return True
        if attempt < max_attempts - 1:
            time.sleep(_POLL_INTERVAL)
    warn(f"IAM resources still present after {timeout}s timeout")
    return False


def _force_remove_finalizers(cluster: str) -> None:
    patch_payload = json.dumps({"metadata": {"finalizers": None}})
    for resource, suffix in _IAM_RESOURCES.items():
        name = f"{cluster}-{suffix}"
        info(f"Removing finalizers from {resource} {name}...")
        result = subprocess.run(
            [
                "oc",
                "patch",
                resource,
                name,
                "--type=merge",
                f"-p={patch_payload}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            warn(f"  -> Failed to patch {resource}: {result.stderr}")
        else:
            info(f"  -> {resource} finalizers removed")


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
    _delete_iam_no_wait(cluster)

    info("Waiting for IAM resources to be fully deleted...")
    if not _wait_iam_deleted(cluster):
        warn("Some IAM resources still exist, removing Crossplane finalizers...")
        _force_remove_finalizers(cluster)

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
