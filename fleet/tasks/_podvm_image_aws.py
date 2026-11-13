"""The pod VM image of one coco cluster: build and delete calls, made on the hub.

build-podvm-image-aws selects the disk image among the operator's related images (disk_image),
reuses an AMI or a snapshot built from it (find_image, find_snapshot), or extracts the disk,
converts it to raw, stages it in S3, imports it as a snapshot and registers the AMI
(extract_disk, to_raw, stage, import_snapshot, register, unstage). terminate-pod-vms deletes
the AMIs, their snapshots and the staging bucket (delete_images, unstage).

Every call uses the cluster's installer credential. The AMI and its snapshot carry
<CLUSTER_LABEL>=<cluster>, by which the peer-pods policy allows launches, and
<PODVM_PAYLOAD_TAG>=<digest of the disk image>.
"""

import json
import os
import re
import subprocess
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from fleet.tasks._aws_binding import aws_credentials
from fleet.tasks._aws_components import CLUSTER_LABEL
from fleet.tasks._log import info
from fleet.tasks._podvm_aws import UEFI_BOOT_MODES

# Value: the digest of the disk image the AMI or snapshot was built from ("sha256:<hex>")
PODVM_PAYLOAD_TAG = "openshiftpartnerlabs.com/podvm-payload"
PODVM_DISK_REPOSITORY = "openshift-sandboxed-containers/osc-dm-verity-image"
PODVM_DISK_FILE = "podvm.qcow2"  # under /image in the disk image
BUCKET_SUFFIX = "-podvm-image"  # after the infra ID
IMPORT_ROLE_SUFFIX = "-vmimport-role"  # after the cluster name
RAW_KEY = "podvm.raw"

# <registry>/<PODVM_DISK_REPOSITORY>@sha256:<64 hex>
_DISK_IMAGE = re.compile(
    rf".+/{re.escape(PODVM_DISK_REPOSITORY)}@(sha256:[0-9a-f]{{64}})"
)


class PodVMImageError(RuntimeError):
    """The pod VM image cannot be selected, built or reused."""


def s3_client(cluster: str, region: str, creds_secret: str) -> Any:
    """boto3 S3 client for region with the credential in Secret creds_secret (aws_credentials)."""
    key_id, secret = aws_credentials(cluster, creds_secret)
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )


def _tags(cluster: str, digest: str) -> list[dict[str, str]]:
    return [
        {"Key": CLUSTER_LABEL, "Value": cluster},
        {"Key": PODVM_PAYLOAD_TAG, "Value": digest},
    ]


def _tag_filters(cluster: str, digest: str) -> list[dict[str, Any]]:
    return [
        {"Name": f"tag:{CLUSTER_LABEL}", "Values": [cluster]},
        {"Name": f"tag:{PODVM_PAYLOAD_TAG}", "Values": [digest]},
    ]


def _description(cluster: str, digest: str) -> str:
    return f"{cluster} pod VM image {digest}"


def _image_name(cluster: str, digest: str) -> str:
    return f"{cluster}-podvm-{digest.removeprefix('sha256:')[:12]}"


def disk_image(related_images: list[str]) -> tuple[str, str]:
    """(pull spec, "sha256:<hex>") of the one related image that holds the pod VM disk.

    A candidate is pinned by digest and its repository path ends with PODVM_DISK_REPOSITORY.
    PodVMImageError when there is none (with the related images) or several (with the candidates).
    """
    candidates = [
        (image, match.group(1))
        for image in related_images
        if (match := _DISK_IMAGE.fullmatch(image))
    ]
    if not candidates:
        raise PodVMImageError(
            f"no related image of repository {PODVM_DISK_REPOSITORY} pinned by digest; "
            f"related images: {', '.join(related_images)}"
        )
    if len(candidates) > 1:
        raise PodVMImageError(
            f"{len(candidates)} related images of repository {PODVM_DISK_REPOSITORY}, "
            f"expected 1: {', '.join(image for image, _ in candidates)}"
        )
    return candidates[0]


def find_image(ec2: Any, cluster: str, digest: str) -> str | None:
    """ImageId of the newest available self-owned image with both tags, or None.

    PodVMImageError when its boot mode is not in UEFI_BOOT_MODES (AMD SEV-SNP needs UEFI).
    """
    images = ec2.describe_images(
        Owners=["self"],
        Filters=[
            *_tag_filters(cluster, digest),
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    if not images:
        return None
    # CreationDate is an ISO 8601 UTC string, so the string order is the time order
    image = max(images, key=lambda i: i["CreationDate"])
    ami = image["ImageId"]
    mode = image.get("BootMode", "")
    if mode not in UEFI_BOOT_MODES:
        raise PodVMImageError(
            f"AMI {ami} has boot mode '{mode}'; AMD SEV-SNP needs uefi or uefi-preferred"
        )
    return ami


def find_snapshot(ec2: Any, cluster: str, digest: str) -> str | None:
    """SnapshotId of the newest completed self-owned snapshot with both tags, or None."""
    snapshots = ec2.describe_snapshots(
        OwnerIds=["self"],
        Filters=[
            *_tag_filters(cluster, digest),
            {"Name": "status", "Values": ["completed"]},
        ],
    )["Snapshots"]
    if not snapshots:
        return None
    return max(snapshots, key=lambda s: s["StartTime"])["SnapshotId"]


def extract_disk(image: str, registry_config: str, work_dir: str) -> str:
    """Extract /image of the disk image to <work_dir>/image; returns the path of PODVM_DISK_FILE.

    registry_config is a file with the registry credentials (a pull secret). PodVMImageError when
    oc fails, or when PODVM_DISK_FILE is absent (with the files that were extracted).
    """
    target = os.path.join(work_dir, "image")
    os.makedirs(target, exist_ok=True)
    result = subprocess.run(
        [
            "oc",
            "image",
            "extract",
            image,
            "--path",
            f"/image/:{target}",
            "--registry-config",
            registry_config,
            "--filter-by-os",
            "linux/amd64",
            "--confirm",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PodVMImageError(
            f"oc image extract {image} failed: {result.stderr.strip()}"
        )
    disk = os.path.join(target, PODVM_DISK_FILE)
    if not os.path.isfile(disk):
        found = sorted(
            os.path.relpath(os.path.join(root, name), target)
            for root, _, names in os.walk(target)
            for name in names
        )
        raise PodVMImageError(
            f"/image/{PODVM_DISK_FILE} not found in {image}; "
            f"files under /image: {', '.join(found) or 'none'}"
        )
    return disk


def to_raw(disk: str, work_dir: str) -> str:
    """Path of the disk in raw format: disk itself when raw, <work_dir>/RAW_KEY when qcow2.

    Logs the file size and the virtual size. PodVMImageError for any other format and when
    qemu-img fails.
    """
    result = subprocess.run(
        ["qemu-img", "info", "--output", "json", disk],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PodVMImageError(f"qemu-img info failed: {result.stderr.strip()}")
    try:
        described = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PodVMImageError(f"qemu-img info returned no JSON: {exc}") from exc
    fmt = described.get("format")
    info(
        f"{disk}: format {fmt}, file size {os.path.getsize(disk)} bytes, "
        f"virtual size {described.get('virtual-size')} bytes"
    )
    if fmt == "raw":
        return disk
    if fmt != "qcow2":
        raise PodVMImageError(f"{disk} has format '{fmt}'; expected qcow2 or raw")
    raw = os.path.join(work_dir, RAW_KEY)
    result = subprocess.run(
        ["qemu-img", "convert", "-f", "qcow2", "-O", "raw", disk, raw],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PodVMImageError(f"qemu-img convert failed: {result.stderr.strip()}")
    return raw


def stage(s3: Any, bucket: str, region: str, raw: str) -> None:
    """Create the private bucket in region and upload raw as RAW_KEY.

    A bucket the account already owns is reused; a bucket of another account is a ClientError.
    """
    request: dict[str, Any] = {"Bucket": bucket}
    # us-east-1 is the default location and rejects a LocationConstraint
    if region != "us-east-1":
        request["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        s3.create_bucket(**request)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.upload_file(raw, bucket, RAW_KEY)


def unstage(s3: Any, bucket: str) -> None:
    """Delete RAW_KEY and the bucket. An absent bucket is not an error."""
    try:
        s3.delete_object(Bucket=bucket, Key=RAW_KEY)
        s3.delete_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchBucket":
            raise


def import_snapshot(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    ec2: Any,
    bucket: str,
    role: str,
    cluster: str,
    digest: str,
    poll_seconds: int = 15,
    attempts: int = 240,
) -> str:
    """Import RAW_KEY of bucket as an EBS snapshot with both tags; returns the SnapshotId.

    role is the name of the service role that VM Import assumes to read the bucket.
    PodVMImageError when the import task is deleted or deleting (with its StatusMessage) and when
    it has not completed after attempts polls.
    """
    description = _description(cluster, digest)
    tags = _tags(cluster, digest)
    task_id = ec2.import_snapshot(
        Description=description,
        DiskContainer={
            "Description": description,
            "Format": "RAW",
            "UserBucket": {"S3Bucket": bucket, "S3Key": RAW_KEY},
        },
        RoleName=role,
        TagSpecifications=[{"ResourceType": "import-snapshot-task", "Tags": tags}],
    )["ImportTaskId"]
    info(f"import task {task_id} started")
    for _ in range(attempts):
        tasks = ec2.describe_import_snapshot_tasks(ImportTaskIds=[task_id])[
            "ImportSnapshotTasks"
        ]
        # A task that was just created can be missing from the first answers
        detail = tasks[0]["SnapshotTaskDetail"] if tasks else {}
        status = detail.get("Status")
        if status == "completed":
            break
        if status in ("deleted", "deleting"):
            raise PodVMImageError(
                f"import task {task_id} is {status}: {detail.get('StatusMessage', '')}"
            )
        time.sleep(poll_seconds)
    else:
        raise PodVMImageError(
            f"import task {task_id} did not complete within {attempts * poll_seconds} s"
        )
    snapshot_id: str = detail["SnapshotId"]
    # ImportSnapshot tags the task only; the peer-pods policy reads the tag on the snapshot
    ec2.create_tags(Resources=[snapshot_id], Tags=tags)
    ec2.get_waiter("snapshot_completed").wait(SnapshotIds=[snapshot_id])
    info(f"import task {task_id} completed: snapshot {snapshot_id}")
    return snapshot_id


def register(ec2: Any, cluster: str, digest: str, snapshot_id: str) -> str:
    """Register the AMI <cluster>-podvm-<first 12 hex of digest> on snapshot_id; returns the ImageId.

    The settings are those of the operator's image creation: x86_64, hvm, ENA, UEFI boot, TPM 2.0,
    root device /dev/xvda. A name that already exists resolves to that image when it carries both
    tags and is a PodVMImageError otherwise.
    """
    name = _image_name(cluster, digest)
    tags = _tags(cluster, digest)
    try:
        ami: str = ec2.register_image(
            Name=name,
            Description=_description(cluster, digest),
            Architecture="x86_64",
            RootDeviceName="/dev/xvda",
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/xvda",
                    "Ebs": {"SnapshotId": snapshot_id, "DeleteOnTermination": True},
                }
            ],
            VirtualizationType="hvm",
            EnaSupport=True,
            BootMode="uefi",
            TpmSupport="v2.0",
            TagSpecifications=[{"ResourceType": "image", "Tags": tags}],
        )["ImageId"]
        return ami
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidAMIName.Duplicate":
            raise
    existing = ec2.describe_images(
        Owners=["self"], Filters=[{"Name": "name", "Values": [name]}]
    )["Images"]
    for image in existing:
        if all(tag in image.get("Tags", []) for tag in tags):
            found: str = image["ImageId"]
            return found
    raise PodVMImageError(
        f"AMI name {name} is taken by an image without the tags "
        f"{CLUSTER_LABEL}={cluster} and {PODVM_PAYLOAD_TAG}={digest}"
    )


def delete_images(ec2: Any, cluster: str) -> tuple[int, int]:
    """Delete the cluster's pod VM images; returns (AMIs deregistered, snapshots deleted).

    An AMI or snapshot belongs to the set when it is self-owned and carries
    <CLUSTER_LABEL>=<cluster> and the key PODVM_PAYLOAD_TAG with any value. The snapshots of
    those AMIs are deleted with or without the tags. A snapshot of a persistent volume carries
    the cluster tag only and is not in the set.
    """
    filters = [
        {"Name": f"tag:{CLUSTER_LABEL}", "Values": [cluster]},
        {"Name": "tag-key", "Values": [PODVM_PAYLOAD_TAG]},
    ]
    images = ec2.describe_images(Owners=["self"], Filters=filters)["Images"]
    snapshot_ids: set[str] = set()
    for image in images:
        snapshot_ids.update(
            mapping["Ebs"]["SnapshotId"]
            for mapping in image.get("BlockDeviceMappings", [])
            if mapping.get("Ebs", {}).get("SnapshotId")
        )
        ec2.deregister_image(ImageId=image["ImageId"])
    snapshots = ec2.describe_snapshots(OwnerIds=["self"], Filters=filters)["Snapshots"]
    snapshot_ids.update(snapshot["SnapshotId"] for snapshot in snapshots)
    deleted = 0
    for snapshot_id in sorted(snapshot_ids):
        try:
            ec2.delete_snapshot(SnapshotId=snapshot_id)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidSnapshot.NotFound":
                raise
        else:
            deleted += 1
    return len(images), deleted
