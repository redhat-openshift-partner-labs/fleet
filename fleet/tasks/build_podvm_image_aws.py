"""Build the pod VM image of one cluster from the operator's disk image (coco tier, AWS).

CLI: fleet-build-podvm-image-aws --cluster-name NAME --spoke-kubeconfig PATH --work-dir DIR
Reads the cluster's region, infra ID and installer credential from the hub and the related
images of the sandboxed containers operator from the spoke's catalog. The disk image is the
related image of repository PODVM_DISK_REPOSITORY; its digest is the payload.

An available AMI of the cluster with that payload is returned. Otherwise a completed snapshot
with that payload is registered. Otherwise the disk is extracted with the spoke's pull secret,
converted to raw in DIR, uploaded to the bucket <infraID>-podvm-image, imported as a snapshot
through the role <cluster>-vmimport-role and registered.

The pull secret file has mode 0600, lives in DIR and is removed when the extraction ends. The
disk files, the uploaded object and the bucket are removed when the build ends, on success and
on failure; a cleanup that fails is a warning, and terminate-pod-vms deletes the bucket.

Prints one JSON object to stdout: ami-id, podvm-payload. Log lines go to stderr. Exits 1 on any
failure.
"""

import argparse
import base64
import binascii
import json
import os
import shutil
import subprocess
import sys
from typing import Any

from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_binding import cluster_facts
from fleet.tasks._log import configure, error, info, warn
from fleet.tasks._operator_catalog import channel_related_images
from fleet.tasks._podvm_aws import ec2_client
from fleet.tasks._podvm_image_aws import (
    BUCKET_SUFFIX,
    IMPORT_ROLE_SUFFIX,
    RAW_KEY,
    PodVMImageError,
    disk_image,
    extract_disk,
    find_image,
    find_snapshot,
    import_snapshot,
    register,
    s3_client,
    stage,
    to_raw,
    unstage,
)
from fleet.tasks.apply_coco_workloads import OSC_PACKAGE

# The Subscription in workloads/coco/subscription.yaml
OSC_CHANNEL = "stable"
OSC_SOURCE = "redhat-operators"

# A file name under --work-dir
_PULL_SECRET_FILE = "pull-secret.json"  # nosec B105


def _pull_secret(spoke_kubeconfig: str) -> str:
    """The .dockerconfigjson of the spoke's Secret openshift-config/pull-secret, decoded."""
    result = subprocess.run(
        [
            "oc",
            "get",
            "secret",
            "pull-secret",
            "-n",
            "openshift-config",
            "-o",
            "json",
            f"--kubeconfig={spoke_kubeconfig}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)["data"]
    return base64.b64decode(data[".dockerconfigjson"]).decode()


def _remove(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def _write_private(path: str, content: str) -> None:
    """Write content to a new file of mode 0600; a file already at path is replaced."""
    _remove(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)


def _extract(image: str, spoke_kubeconfig: str, work_dir: str) -> str:
    """extract_disk with the spoke's pull secret; the pull secret file exists only meanwhile."""
    registry_config = os.path.join(work_dir, _PULL_SECRET_FILE)
    content = _pull_secret(spoke_kubeconfig)
    try:
        _write_private(registry_config, content)
        return extract_disk(image, registry_config, work_dir)
    finally:
        _remove(registry_config)


def _clean_up(s3: Any, bucket: str, work_dir: str) -> None:
    """Remove the disk files, the staged object and the bucket; an S3 failure is a warning."""
    shutil.rmtree(os.path.join(work_dir, "image"), ignore_errors=True)
    _remove(os.path.join(work_dir, RAW_KEY))
    try:
        unstage(s3, bucket)
    except (ClientError, BotoCoreError) as exc:
        warn(f"bucket {bucket} was not deleted: {exc}")


def _import(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ec2: Any,
    s3: Any,
    cluster: str,
    infra_id: str,
    region: str,
    image: str,
    digest: str,
    spoke_kubeconfig: str,
    work_dir: str,
) -> str:
    """SnapshotId of the disk image, imported through the staging bucket."""
    bucket = f"{infra_id}{BUCKET_SUFFIX}"
    try:
        disk = _extract(image, spoke_kubeconfig, work_dir)
        raw = to_raw(disk, work_dir)
        info(f"  -> uploading {raw} to bucket {bucket}")
        stage(s3, bucket, region, raw)
        return import_snapshot(
            ec2, bucket, f"{cluster}{IMPORT_ROLE_SUFFIX}", cluster, digest
        )
    finally:
        _clean_up(s3, bucket, work_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--work-dir", required=True)
    args = parser.parse_args()

    configure("build-podvm-image-aws")

    cluster = args.cluster_name
    info("=== Building the pod VM image ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")
    info(f"  work-dir={args.work_dir}")

    try:
        infra_id, region, creds_secret = cluster_facts(cluster)
        ec2 = ec2_client(cluster, region, creds_secret)
        s3 = s3_client(cluster, region, creds_secret)
        image, digest = disk_image(
            channel_related_images(
                OSC_PACKAGE, OSC_CHANNEL, OSC_SOURCE, args.spoke_kubeconfig
            )
        )
        info(f"  -> disk image: {image}")
        ami_id = find_image(ec2, cluster, digest)
        if ami_id:
            info(f"  -> reusing AMI {ami_id}")
        else:
            snapshot_id = find_snapshot(ec2, cluster, digest)
            if snapshot_id:
                info(f"  -> reusing snapshot {snapshot_id}")
            else:
                snapshot_id = _import(
                    ec2,
                    s3,
                    cluster,
                    infra_id,
                    region,
                    image,
                    digest,
                    args.spoke_kubeconfig,
                    args.work_dir,
                )
            ami_id = register(ec2, cluster, digest, snapshot_id)
            info(f"  -> registered AMI {ami_id} on snapshot {snapshot_id}")
    except subprocess.CalledProcessError as exc:
        error(f"Failed to build the pod VM image: {exc}: {(exc.stderr or '').strip()}")
        sys.exit(1)
    except (
        PodVMImageError,
        ValueError,
        KeyError,
        binascii.Error,
        OSError,
        ClientError,
        BotoCoreError,
        Boto3Error,
    ) as exc:
        error(f"Failed to build the pod VM image: {exc}")
        sys.exit(1)

    print(json.dumps({"ami-id": ami_id, "podvm-payload": digest}))
