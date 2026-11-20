"""Capture and retain follow-up for IAM resources bypassed during deprovision."""

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._log import warn

CROSSPLANE_FINALIZER = "finalizer.managedresource.crossplane.io"
PIPELINE_NAMESPACE = "openshift-pipelines"
REPORT_LABEL = "openshiftpartnerlabs.com/iam-cleanup-cluster"
REPORT_FILE = "iam.cleanup.json"
SCHEMA_VERSION = 1
_IAM_READ_BUDGET = 8


class CleanupError(RuntimeError):
    """IAM cleanup could not safely proceed."""


def oc(*args: str, timeout: float = 30, data: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["oc", *args], input=data, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise CleanupError(f"oc {args[0]} timed out") from exc
    if result.returncode:
        raise CleanupError(f"oc {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def resource_ref(item: dict) -> str:
    return f"{item['kind'].lower()}.iam/{item['metadata']['name']}"


def read_resources(targets: list[str]) -> dict[str, dict]:
    if not targets:
        return {}
    output = oc("get", *targets, "--ignore-not-found", "-o", "json")
    if not output.strip():
        return {}
    document = json.loads(output)
    items = document["items"] if document.get("kind") == "List" else [document]
    return {resource_ref(item): item for item in items}


def _release_finalizer(item: dict) -> None:
    metadata = item["metadata"]
    target = resource_ref(item)
    deletion_timestamp = metadata.get("deletionTimestamp")
    if not deletion_timestamp:
        raise CleanupError(f"Deletion has not been requested for {target}")
    finalizers = metadata.get("finalizers", [])
    if CROSSPLANE_FINALIZER not in finalizers:
        return

    path = f"/metadata/finalizers/{finalizers.index(CROSSPLANE_FINALIZER)}"
    patch = [
        {"op": "test", "path": "/metadata/uid", "value": metadata["uid"]},
        {
            "op": "test",
            "path": "/metadata/deletionTimestamp",
            "value": deletion_timestamp,
        },
        {"op": "test", "path": path, "value": CROSSPLANE_FINALIZER},
        {"op": "remove", "path": path},
    ]
    try:
        oc("patch", target, "--type=json", "-p", json.dumps(patch))
    except CleanupError:
        if oc("get", target, "--ignore-not-found", "-o", "name").strip():
            raise


def release_finalizers(items: list[dict]) -> None:
    for item in items:
        _release_finalizer(item)


def _iam_reader() -> tuple[Any, str]:
    account = os.environ.get("FLEET_IAM_AWS_ACCOUNT", "")
    if not account or not os.environ.get("AWS_ACCESS_KEY_ID"):
        return None, ""
    config = Config(
        connect_timeout=2, read_timeout=2, retries={"total_max_attempts": 1}
    )
    try:
        identity = boto3.client("sts", config=config).get_caller_identity()
        if identity["Account"] == account:
            return boto3.client("iam", config=config), account
    except (BotoCoreError, ClientError) as exc:
        warn(f"AWS IAM reader unavailable ({type(exc).__name__})")
    return None, account


def _aws_state(iam: Any, item: dict, account: str, deadline: float) -> tuple[str, str]:
    if iam is None:
        return "needs_check", "AWSReadIdentityUnavailable"
    if time.monotonic() >= deadline:
        return "needs_check", "AWSReadDeadlineExceeded"

    kind = item["kind"]
    arn = item["arn"]
    name = item["external_name"]
    if arn and arn.split(":")[4:5] != [account]:
        return "needs_check", "AWSAccountMismatch"
    try:
        if kind == "User" and name:
            iam.get_user(UserName=name)
        elif kind == "Role" and name:
            iam.get_role(RoleName=name)
        elif kind == "Policy" and arn:
            iam.get_policy(PolicyArn=arn)
        else:
            return "needs_check", "AWSResourceLookupUnavailable"
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        return ("", "") if code == "NoSuchEntity" else ("needs_check", code)
    except BotoCoreError as exc:
        return "needs_check", type(exc).__name__
    return "confirmed_present", "AWSReadSucceeded"


def _item_details(resource: dict) -> dict:
    metadata = resource["metadata"]
    status = resource.get("status", {})
    external_name = metadata.get("annotations", {}).get(
        "crossplane.io/external-name", ""
    )
    arn = status.get("atProvider", {}).get("arn", "")
    return {
        "resource": resource_ref(resource),
        "kind": resource["kind"],
        "uid": metadata.get("uid", ""),
        "external_name": external_name,
        "arn": arn or (external_name if external_name.startswith("arn:") else ""),
        "conditions": {
            condition["type"]: condition.get("reason", condition.get("status", ""))
            for condition in status.get("conditions", [])
        },
    }


def build_report(
    cluster: str, run_id: str, infra_id: str, resources: list[dict]
) -> dict:
    deadline = time.monotonic() + _IAM_READ_BUDGET
    iam, account = _iam_reader()
    report_items = []
    for resource in resources:
        item = _item_details(resource)
        state, reason = _aws_state(iam, item, account, deadline)
        if state:
            report_items.append(
                {
                    **item,
                    "state": state,
                    "reason": reason,
                    "aws_account": (item["arn"].split(":") + [""] * 5)[4] or account,
                    "pipeline_run_id": run_id,
                    "infra_id": infra_id,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "cluster_name": cluster,
        "items": report_items,
    }


def save_report(report: dict) -> str:
    contents = json.dumps(report, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(contents.encode()).hexdigest()[:32]
    name = f"iam-cleanup-{digest}"
    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": name,
            "namespace": PIPELINE_NAMESPACE,
            "labels": {REPORT_LABEL: report["cluster_name"]},
        },
        "immutable": True,
        "data": {REPORT_FILE: contents},
    }
    oc("apply", "--server-side", "-f", "-", data=json.dumps(document))
    return name


def load_report(cluster: str) -> dict:
    output = oc(
        "get",
        "configmaps",
        "-n",
        PIPELINE_NAMESPACE,
        "-l",
        f"{REPORT_LABEL}={cluster}",
        "-o",
        "json",
    )
    observations: dict[tuple[str, str], dict] = {}
    for configmap in json.loads(output)["items"]:
        report = json.loads(configmap["data"][REPORT_FILE])
        if (
            report["schema_version"] != SCHEMA_VERSION
            or report["cluster_name"] != cluster
        ):
            raise CleanupError(f"Invalid IAM cleanup report for {cluster}")
        for item in report["items"]:
            key = (item["resource"], item["uid"])
            if (
                key not in observations
                or item["observed_at"] >= observations[key]["observed_at"]
            ):
                observations[key] = item
    return {
        "schema_version": SCHEMA_VERSION,
        "cluster_name": cluster,
        "items": [observations[key] for key in sorted(observations)],
    }
