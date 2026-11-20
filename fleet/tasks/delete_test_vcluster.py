"""Delete a test vCluster and the hub resources of its test run.

CLI: fleet-delete-test-vcluster --cluster-name NAME --namespace NAMESPACE
The finally task of test-vcluster. Exits 1 and deletes nothing when NAME belongs to
a real cluster. Otherwise it attempts every deletion and exits 1 when one failed.
"""

import argparse
import subprocess
import sys
import time

from fleet.tasks._log import configure, error, info, warn
from fleet.tasks._test_vcluster import (
    FOREIGN,
    OWNED,
    OWNER_LABEL,
    has_vcluster,
    namespace_state,
    refusal,
)

# save-spoke-kubeconfig and create-cluster-cronjob of post-provision write here.
KUBECONFIG_NAMESPACE = "openshift-pipelines"
CRONJOB_NAMESPACE = "default"


def _delete(kind: str, name: str, *options: str) -> list[str]:
    """Delete one object. Returns the failure, or nothing when the object is gone."""
    result = subprocess.run(
        ["oc", "delete", kind, name, "--ignore-not-found=true", *options],
        capture_output=True,
        text=True,
    )
    info(f"  -> {kind} delete exit code: {result.returncode}")
    if result.returncode != 0:
        return [f"{kind} {name}: {result.stderr.strip()}"]
    return []


def _wait_for_managedcluster_removal(cluster: str) -> None:
    info("Waiting for ManagedCluster to be fully removed...")
    for _ in range(60):
        result = subprocess.run(
            ["oc", "get", "managedcluster", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            info("  -> ManagedCluster gone")
            return
        time.sleep(5)
    info("  -> ManagedCluster still present after 300s, proceeding anyway")


def _delete_vcluster(cluster: str, namespace: str) -> list[str]:
    """Delete the Route and the vCluster. Returns the failures."""
    result = subprocess.run(
        ["oc", "get", "namespace", namespace], capture_output=True, text=True
    )
    if result.returncode != 0:
        info(f"Namespace '{namespace}' already removed, skipping vcluster delete")
        return []

    info(f"Deleting Route '{cluster}' in namespace '{namespace}'...")
    failures = _delete("route", cluster, "-n", namespace)

    info(f"Deleting vCluster '{cluster}'...")
    result = subprocess.run(
        ["vcluster", "delete", cluster, "-n", namespace],
        capture_output=True,
        text=True,
    )
    info(f"  -> vcluster delete exit code: {result.returncode}")
    if result.returncode == 0:
        return failures

    # The namespace is deleted only when it holds this vCluster. vcluster delete also
    # fails when create-test-vcluster did not run, and the namespace may hold other work.
    try:
        present = has_vcluster(cluster, namespace)
    except RuntimeError as exc:
        return failures + [f"vcluster {cluster}: {exc}"]
    if not present:
        info(f"No vCluster '{cluster}' in namespace '{namespace}'; namespace kept")
        return failures

    info(
        f"vcluster delete failed ({result.stderr.strip()}), falling back to namespace delete"
    )
    return failures + _delete("namespace", namespace)


def _delete_test_namespace(cluster: str) -> list[str]:
    """Delete the namespace of the hub resources when a test created it."""
    try:
        state = namespace_state(cluster)
    except RuntimeError as exc:
        return [f"namespace {cluster}: {exc}"]
    if state == OWNED:
        info(f"Deleting namespace '{cluster}'...")
        return _delete("namespace", cluster, "--timeout=300s")
    if state == FOREIGN:
        warn(
            f"Namespace '{cluster}' does not carry the label {OWNER_LABEL}={cluster}; kept"
        )
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("delete-test-vcluster")

    info("=== Deleting test vCluster ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  namespace={args.namespace}")

    reason = refusal(cluster)
    if reason:
        error(f"{reason}; '{cluster}' is not a test vCluster, nothing deleted")
        sys.exit(1)

    info(f"Deleting ManagedCluster '{cluster}'...")
    failures = _delete("managedcluster", cluster)
    _wait_for_managedcluster_removal(cluster)

    failures += _delete_vcluster(cluster, args.namespace)
    failures += _delete_test_namespace(cluster)

    info(f"Deleting CronJob '{cluster}' in namespace '{CRONJOB_NAMESPACE}'...")
    failures += _delete("cronjob", cluster, "-n", CRONJOB_NAMESPACE)

    info(f"Deleting Secret '{cluster}-spoke-kubeconfig'...")
    failures += _delete(
        "secret", f"{cluster}-spoke-kubeconfig", "-n", KUBECONFIG_NAMESPACE
    )

    if failures:
        for failure in failures:
            error(f"Not deleted: {failure}")
        sys.exit(1)
    info("Delete complete")
