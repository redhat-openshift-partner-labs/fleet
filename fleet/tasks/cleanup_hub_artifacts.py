"""Clean up hub-side artifacts after Hive completes deprovision."""

import argparse
import json
import subprocess
import sys
import time

from fleet.tasks._aws_components import DiscoveryError, all_iam_targets
from fleet.tasks import _iam_cleanup as iam
from fleet.tasks._log import configure, error, info, warn

_POLL_INTERVAL = 10
_POLL_TIMEOUT = 600


def _delete_iam_no_wait(targets: list[str]) -> None:
    info(f"Deleting {len(targets)} IAM resources")
    try:
        iam.oc("delete", *targets, "--wait=false", "--ignore-not-found=true")
    except iam.CleanupError as exc:
        warn(f"{exc}. Checking which resources remain.")


def _wait_iam_deleted(targets: list[str], timeout: int) -> list[str]:
    deadline = time.monotonic() + timeout
    remaining = targets
    attempts = (timeout + _POLL_INTERVAL - 1) // _POLL_INTERVAL
    for attempt in range(attempts):
        budget = deadline - time.monotonic()
        if budget <= 0:
            break
        try:
            output = iam.oc(
                "get",
                *targets,
                "--ignore-not-found",
                "-o",
                "name",
                timeout=min(30, budget),
            )
        except iam.CleanupError as exc:
            warn(str(exc))
            remaining = targets
        else:
            remaining = output.split()
            if not remaining:
                return []
        if attempt + 1 < attempts:
            time.sleep(max(0, min(_POLL_INTERVAL, deadline - time.monotonic())))
    return remaining


def _describe_stuck(remaining: list[str]) -> None:
    try:
        for item in iam.read_resources(remaining).values():
            name = (
                item["metadata"]
                .get("annotations", {})
                .get("crossplane.io/external-name")
            )
            conditions = item.get("status", {}).get("conditions", [])
            summary = {
                c["type"]: c.get("message") or c.get("reason") for c in conditions
            }
            warn(f"{iam.resource_ref(item)} (AWS name: {name}): {summary}")
    except iam.CleanupError as exc:
        warn(f"{exc}. Last known targets: {', '.join(remaining)}")


def _report_and_release(
    args: argparse.Namespace, remaining: list[str], inventory: dict[str, dict]
) -> None:
    try:
        current = iam.read_resources(remaining)
    except iam.CleanupError as exc:
        candidates = {
            target.replace(".iam.aws.upbound.io/", ".iam/") for target in remaining
        }
        resources = [item for ref, item in inventory.items() if ref in candidates]
        if resources:
            _save_report(args, resources)
        raise iam.CleanupError(
            "Could not confirm which Crossplane objects are pending deletion"
        ) from exc

    for ref, item in current.items():
        if (
            inventory.get(ref, {}).get("metadata", {}).get("uid")
            != item["metadata"]["uid"]
        ):
            raise iam.CleanupError(f"IAM object changed during deletion: {ref}")
    resources = list(current.values())
    if resources:
        _save_report(args, resources)
        iam.release_finalizers(resources)


def _save_report(args: argparse.Namespace, resources: list[dict]) -> None:
    report = iam.build_report(
        args.cluster_name, args.pipeline_run_id, args.infra_id, resources
    )
    if report["items"]:
        name = iam.save_report(report)
        warn(f"IAM cleanup follow-up saved in {iam.PIPELINE_NAMESPACE}/{name}")
        print(json.dumps(report, indent=2))


def _cleanup_iam(args: argparse.Namespace) -> None:
    cluster = args.cluster_name
    targets = all_iam_targets(cluster)
    inventory = iam.read_resources(targets) if args.orphan_stuck_iam else {}
    _delete_iam_no_wait(targets)
    remaining = _wait_iam_deleted(targets, args.iam_timeout_seconds)
    if not remaining:
        info("All Crossplane IAM resources deleted")
    elif args.orphan_stuck_iam:
        _report_and_release(args, remaining, inventory)
    else:
        _describe_stuck(remaining)
        raise iam.CleanupError(
            f"{len(remaining)} IAM resources remain. Fix the Crossplane error and retry, "
            "or rerun with orphan-stuck-iam=true to preserve a follow-up report."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--iam-timeout-seconds", type=int, default=_POLL_TIMEOUT)
    parser.add_argument("--orphan-stuck-iam", action="store_true")
    parser.add_argument("--pipeline-run-id", default="manual")
    parser.add_argument("--infra-id", default="")
    args = parser.parse_args()
    if args.iam_timeout_seconds <= 0:
        parser.error("--iam-timeout-seconds must be positive")

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

    try:
        _cleanup_iam(args)
    except (DiscoveryError, iam.CleanupError, ValueError, KeyError) as exc:
        error(
            f"{exc}; namespace {cluster} kept. Re-run deprovision after fixing the error."
        )
        sys.exit(1)

    info(f"Deleting CronJob {cluster} from default namespace...")
    cronjob_result = subprocess.run(
        [
            "oc",
            "delete",
            "cronjob",
            cluster,
            "-n",
            "default",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> CronJob delete exit code: {cronjob_result.returncode}")
    if cronjob_result.returncode != 0:
        error(f"Failed to delete CronJob {cluster}: {cronjob_result.stderr}")
        sys.exit(1)

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
