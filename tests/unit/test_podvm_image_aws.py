import datetime
import json
import subprocess
from unittest import mock

import pytest
from botocore.exceptions import ClientError

from fleet.tasks._aws_components import CLUSTER_LABEL
from fleet.tasks._podvm_image_aws import (
    BUCKET_SUFFIX,
    IMPORT_ROLE_SUFFIX,
    PODVM_DISK_FILE,
    PODVM_DISK_REPOSITORY,
    PODVM_PAYLOAD_TAG,
    RAW_KEY,
    PodVMImageError,
    delete_images,
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

REGION = "us-east-2"
CLUSTER = "c1"
HEX = "0123456789ab" + "c" * 52
DIGEST = f"sha256:{HEX}"
DISK_IMAGE = f"registry.redhat.io/{PODVM_DISK_REPOSITORY}@{DIGEST}"
OPERATOR_IMAGE = (
    "registry.redhat.io/openshift-sandboxed-containers/osc-rhel9-operator@sha256:"
    + "a" * 64
)
BUCKET = "c1-abcde-podvm-image"
ROLE = "c1-vmimport-role"
TAGS = [
    {"Key": CLUSTER_LABEL, "Value": CLUSTER},
    {"Key": PODVM_PAYLOAD_TAG, "Value": DIGEST},
]
TAG_FILTERS = [
    {"Name": f"tag:{CLUSTER_LABEL}", "Values": [CLUSTER]},
    {"Name": f"tag:{PODVM_PAYLOAD_TAG}", "Values": [DIGEST]},
]
TEARDOWN_FILTERS = [
    {"Name": f"tag:{CLUSTER_LABEL}", "Values": [CLUSTER]},
    {"Name": "tag-key", "Values": [PODVM_PAYLOAD_TAG]},
]


def _client_error(code, operation="Operation"):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr):
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


def test_scaffold_contract_strings():
    """The scaffold's policies name the tag, the bucket and the role by these strings."""
    assert PODVM_PAYLOAD_TAG == "openshiftpartnerlabs.com/podvm-payload"
    assert PODVM_DISK_REPOSITORY == "openshift-sandboxed-containers/osc-dm-verity-image"
    assert PODVM_DISK_FILE == "podvm.qcow2"
    assert BUCKET_SUFFIX == "-podvm-image"
    assert IMPORT_ROLE_SUFFIX == "-vmimport-role"
    assert RAW_KEY == "podvm.raw"


# ---------------------------------------------------------------------------
# Selection and lookup
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks._podvm_image_aws.aws_credentials")
@mock.patch("fleet.tasks._podvm_image_aws.boto3")
def test_s3_client_uses_the_cluster_credential(mock_boto3, mock_credentials):
    mock_credentials.return_value = ("AKIAEXAMPLE", "s3cr3t")
    assert s3_client(CLUSTER, REGION, "aws-creds") is mock_boto3.client.return_value
    mock_credentials.assert_called_once_with(CLUSTER, "aws-creds")
    mock_boto3.client.assert_called_once_with(
        "s3",
        region_name=REGION,
        aws_access_key_id="AKIAEXAMPLE",
        aws_secret_access_key="s3cr3t",
    )


def test_disk_image_returns_pull_spec_and_digest():
    assert disk_image([OPERATOR_IMAGE, DISK_IMAGE]) == (DISK_IMAGE, DIGEST)


@pytest.mark.parametrize(
    "other",
    [
        f"registry.redhat.io/{PODVM_DISK_REPOSITORY}:1.12",
        f"registry.redhat.io/{PODVM_DISK_REPOSITORY}@sha256:abc",
        f"registry.redhat.io/{PODVM_DISK_REPOSITORY}-extra@{DIGEST}",
        f"registry.redhat.io/x-{PODVM_DISK_REPOSITORY}@{DIGEST}",
    ],
    ids=["tag", "short-digest", "longer-repository", "other-namespace"],
)
def test_disk_image_ignores_other_references(other):
    assert disk_image([other, DISK_IMAGE]) == (DISK_IMAGE, DIGEST)
    with pytest.raises(PodVMImageError):
        disk_image([other])


def test_disk_image_fails_without_a_candidate():
    with pytest.raises(PodVMImageError) as exc:
        disk_image([OPERATOR_IMAGE])
    assert str(exc.value) == (
        f"no related image of repository {PODVM_DISK_REPOSITORY} pinned by digest; "
        f"related images: {OPERATOR_IMAGE}"
    )


def test_disk_image_fails_with_several_candidates():
    mirror = f"mirror.example.com/{PODVM_DISK_REPOSITORY}@sha256:{'d' * 64}"
    with pytest.raises(PodVMImageError) as exc:
        disk_image([DISK_IMAGE, OPERATOR_IMAGE, mirror])
    assert str(exc.value) == (
        f"2 related images of repository {PODVM_DISK_REPOSITORY}, expected 1: "
        f"{DISK_IMAGE}, {mirror}"
    )


def test_find_image_returns_the_newest_available_image():
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {
        "Images": [
            {
                "ImageId": "ami-old",
                "CreationDate": "2026-11-01T00:00:00.000Z",
                "BootMode": "uefi",
            },
            {
                "ImageId": "ami-new",
                "CreationDate": "2026-11-12T00:00:00.000Z",
                "BootMode": "uefi-preferred",
            },
        ]
    }
    assert find_image(ec2, CLUSTER, DIGEST) == "ami-new"
    ec2.describe_images.assert_called_once_with(
        Owners=["self"],
        Filters=[*TAG_FILTERS, {"Name": "state", "Values": ["available"]}],
    )


def test_find_image_returns_none_when_absent():
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {"Images": []}
    assert find_image(ec2, CLUSTER, DIGEST) is None


@pytest.mark.parametrize("image", [{"BootMode": "legacy-bios"}, {}])
def test_find_image_rejects_other_boot_modes(image):
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {
        "Images": [
            {"ImageId": "ami-1", "CreationDate": "2026-11-12T00:00:00.000Z", **image}
        ]
    }
    with pytest.raises(PodVMImageError) as exc:
        find_image(ec2, CLUSTER, DIGEST)
    mode = image.get("BootMode", "")
    assert str(exc.value) == (
        f"AMI ami-1 has boot mode '{mode}'; AMD SEV-SNP needs uefi or uefi-preferred"
    )


def test_find_snapshot_returns_the_newest_completed_snapshot():
    ec2 = mock.MagicMock()
    ec2.describe_snapshots.return_value = {
        "Snapshots": [
            {"SnapshotId": "snap-old", "StartTime": datetime.datetime(2026, 11, 1)},
            {"SnapshotId": "snap-new", "StartTime": datetime.datetime(2026, 11, 12)},
        ]
    }
    assert find_snapshot(ec2, CLUSTER, DIGEST) == "snap-new"
    ec2.describe_snapshots.assert_called_once_with(
        OwnerIds=["self"],
        Filters=[*TAG_FILTERS, {"Name": "status", "Values": ["completed"]}],
    )


def test_find_snapshot_returns_none_when_absent():
    ec2 = mock.MagicMock()
    ec2.describe_snapshots.return_value = {"Snapshots": []}
    assert find_snapshot(ec2, CLUSTER, DIGEST) is None


# ---------------------------------------------------------------------------
# Disk extraction and conversion
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_extract_disk_runs_oc_image_extract(mock_run, tmp_path):
    target = tmp_path / "image"

    def _extract(*_args, **_kwargs):
        (target / PODVM_DISK_FILE).write_bytes(b"qcow2")
        return _ok()

    mock_run.side_effect = _extract

    disk = extract_disk(DISK_IMAGE, "/scratch/pull-secret.json", str(tmp_path))

    assert disk == str(target / PODVM_DISK_FILE)
    mock_run.assert_called_once_with(
        [
            "oc",
            "image",
            "extract",
            DISK_IMAGE,
            "--path",
            f"/image/:{target}",
            "--registry-config",
            "/scratch/pull-secret.json",
            "--filter-by-os",
            "linux/amd64",
            "--confirm",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_extract_disk_names_the_files_found(mock_run, tmp_path):
    target = tmp_path / "image"

    def _extract(*_args, **_kwargs):
        (target / "sub").mkdir()
        (target / "sub" / "disk.raw").write_bytes(b"")
        (target / "podvm.img").write_bytes(b"")
        return _ok()

    mock_run.side_effect = _extract

    with pytest.raises(PodVMImageError) as exc:
        extract_disk(DISK_IMAGE, "/scratch/pull-secret.json", str(tmp_path))
    assert str(exc.value) == (
        f"/image/{PODVM_DISK_FILE} not found in {DISK_IMAGE}; "
        "files under /image: podvm.img, sub/disk.raw"
    )


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_extract_disk_reports_an_empty_directory(mock_run, tmp_path):
    mock_run.return_value = _ok()
    with pytest.raises(PodVMImageError) as exc:
        extract_disk(DISK_IMAGE, "/scratch/pull-secret.json", str(tmp_path))
    assert str(exc.value).endswith("files under /image: none")


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_extract_disk_reports_oc_failure(mock_run, tmp_path):
    mock_run.return_value = _fail("error: unauthorized\n")
    with pytest.raises(PodVMImageError) as exc:
        extract_disk(DISK_IMAGE, "/scratch/pull-secret.json", str(tmp_path))
    assert (
        str(exc.value) == f"oc image extract {DISK_IMAGE} failed: error: unauthorized"
    )


def _qemu_info(fmt, virtual_size=1073741824):
    return _ok(json.dumps({"format": fmt, "virtual-size": virtual_size}))


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_converts_qcow2(mock_run, tmp_path, capsys):
    disk = tmp_path / "image" / PODVM_DISK_FILE
    disk.parent.mkdir()
    disk.write_bytes(b"x" * 10)
    mock_run.side_effect = [_qemu_info("qcow2"), _ok()]

    raw = to_raw(str(disk), str(tmp_path))

    assert raw == str(tmp_path / RAW_KEY)
    assert mock_run.call_args_list == [
        mock.call(
            ["qemu-img", "info", "--output", "json", str(disk)],
            capture_output=True,
            text=True,
        ),
        mock.call(
            ["qemu-img", "convert", "-f", "qcow2", "-O", "raw", str(disk), raw],
            capture_output=True,
            text=True,
        ),
    ]
    log = capsys.readouterr().err
    assert "format qcow2, file size 10 bytes, virtual size 1073741824 bytes" in log


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_returns_a_raw_disk_as_is(mock_run, tmp_path):
    disk = tmp_path / "podvm.qcow2"
    disk.write_bytes(b"x")
    mock_run.return_value = _qemu_info("raw")

    assert to_raw(str(disk), str(tmp_path)) == str(disk)
    mock_run.assert_called_once()


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_rejects_other_formats(mock_run, tmp_path):
    disk = tmp_path / "podvm.qcow2"
    disk.write_bytes(b"x")
    mock_run.return_value = _qemu_info("vpc")

    with pytest.raises(PodVMImageError) as exc:
        to_raw(str(disk), str(tmp_path))
    assert str(exc.value) == f"{disk} has format 'vpc'; expected qcow2 or raw"
    mock_run.assert_called_once()


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_reports_qemu_img_info_failure(mock_run, tmp_path):
    mock_run.return_value = _fail("qemu-img: Could not open\n")
    with pytest.raises(PodVMImageError) as exc:
        to_raw(str(tmp_path / "podvm.qcow2"), str(tmp_path))
    assert str(exc.value) == "qemu-img info failed: qemu-img: Could not open"


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_reports_unparsable_info(mock_run, tmp_path):
    mock_run.return_value = _ok("not json")
    with pytest.raises(PodVMImageError) as exc:
        to_raw(str(tmp_path / "podvm.qcow2"), str(tmp_path))
    assert str(exc.value).startswith("qemu-img info returned no JSON: ")


@mock.patch("fleet.tasks._podvm_image_aws.subprocess.run")
def test_to_raw_reports_convert_failure(mock_run, tmp_path):
    disk = tmp_path / "podvm.qcow2"
    disk.write_bytes(b"x")
    mock_run.side_effect = [_qemu_info("qcow2"), _fail("No space left on device\n")]
    with pytest.raises(PodVMImageError) as exc:
        to_raw(str(disk), str(tmp_path))
    assert str(exc.value) == "qemu-img convert failed: No space left on device"


# ---------------------------------------------------------------------------
# Stage and unstage
# ---------------------------------------------------------------------------

PUBLIC_ACCESS_BLOCK = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}


def test_stage_creates_the_bucket_in_the_region():
    s3 = mock.MagicMock()
    stage(s3, BUCKET, REGION, "/scratch/podvm.raw")
    assert s3.mock_calls == [
        mock.call.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
        ),
        mock.call.put_public_access_block(
            Bucket=BUCKET, PublicAccessBlockConfiguration=PUBLIC_ACCESS_BLOCK
        ),
        mock.call.upload_file("/scratch/podvm.raw", BUCKET, RAW_KEY),
    ]


def test_stage_sends_no_location_constraint_in_us_east_1():
    s3 = mock.MagicMock()
    stage(s3, BUCKET, "us-east-1", "/scratch/podvm.raw")
    s3.create_bucket.assert_called_once_with(Bucket=BUCKET)
    s3.upload_file.assert_called_once_with("/scratch/podvm.raw", BUCKET, RAW_KEY)


def test_stage_reuses_a_bucket_the_account_owns():
    s3 = mock.MagicMock()
    s3.create_bucket.side_effect = _client_error("BucketAlreadyOwnedByYou")
    stage(s3, BUCKET, REGION, "/scratch/podvm.raw")
    s3.put_public_access_block.assert_called_once()
    s3.upload_file.assert_called_once_with("/scratch/podvm.raw", BUCKET, RAW_KEY)


def test_stage_fails_on_a_bucket_of_another_account():
    s3 = mock.MagicMock()
    s3.create_bucket.side_effect = _client_error("BucketAlreadyExists")
    with pytest.raises(ClientError):
        stage(s3, BUCKET, REGION, "/scratch/podvm.raw")
    s3.put_public_access_block.assert_not_called()
    s3.upload_file.assert_not_called()


def test_unstage_deletes_the_object_and_the_bucket():
    s3 = mock.MagicMock()
    unstage(s3, BUCKET)
    assert s3.mock_calls == [
        mock.call.delete_object(Bucket=BUCKET, Key=RAW_KEY),
        mock.call.delete_bucket(Bucket=BUCKET),
    ]


def test_unstage_accepts_an_absent_bucket():
    s3 = mock.MagicMock()
    s3.delete_object.side_effect = _client_error("NoSuchBucket")
    unstage(s3, BUCKET)
    s3.delete_bucket.assert_not_called()


def test_unstage_propagates_other_errors():
    s3 = mock.MagicMock()
    s3.delete_bucket.side_effect = _client_error("BucketNotEmpty")
    with pytest.raises(ClientError):
        unstage(s3, BUCKET)


# ---------------------------------------------------------------------------
# Import and register
# ---------------------------------------------------------------------------


def _task(status, **detail):
    return {
        "ImportSnapshotTasks": [
            {
                "ImportTaskId": "import-snap-1",
                "SnapshotTaskDetail": {"Status": status, **detail},
            }
        ]
    }


@mock.patch("fleet.tasks._podvm_image_aws.time.sleep")
def test_import_snapshot_polls_tags_and_waits(mock_sleep):
    ec2 = mock.MagicMock()
    ec2.import_snapshot.return_value = {"ImportTaskId": "import-snap-1"}
    ec2.describe_import_snapshot_tasks.side_effect = [
        {"ImportSnapshotTasks": []},
        _task("active", Progress="40"),
        _task("completed", SnapshotId="snap-1"),
    ]

    assert import_snapshot(ec2, BUCKET, ROLE, CLUSTER, DIGEST) == "snap-1"

    description = f"{CLUSTER} pod VM image {DIGEST}"
    ec2.import_snapshot.assert_called_once_with(
        Description=description,
        DiskContainer={
            "Description": description,
            "Format": "RAW",
            "UserBucket": {"S3Bucket": BUCKET, "S3Key": RAW_KEY},
        },
        RoleName=ROLE,
        TagSpecifications=[{"ResourceType": "import-snapshot-task", "Tags": TAGS}],
    )
    assert (
        ec2.describe_import_snapshot_tasks.call_args_list
        == [mock.call(ImportTaskIds=["import-snap-1"])] * 3
    )
    assert mock_sleep.call_args_list == [mock.call(15), mock.call(15)]
    # The snapshot is tagged before the wait, so a launch is never denied for a missing tag.
    assert ec2.mock_calls[-3:] == [
        mock.call.create_tags(Resources=["snap-1"], Tags=TAGS),
        mock.call.get_waiter("snapshot_completed"),
        mock.call.get_waiter().wait(SnapshotIds=["snap-1"]),
    ]


@pytest.mark.parametrize("status", ["deleted", "deleting"])
@mock.patch("fleet.tasks._podvm_image_aws.time.sleep")
def test_import_snapshot_fails_on_a_deleted_task(mock_sleep, status):
    ec2 = mock.MagicMock()
    ec2.import_snapshot.return_value = {"ImportTaskId": "import-snap-1"}
    ec2.describe_import_snapshot_tasks.return_value = _task(
        status, StatusMessage="ClientError: Disk validation failed"
    )

    with pytest.raises(PodVMImageError) as exc:
        import_snapshot(ec2, BUCKET, ROLE, CLUSTER, DIGEST)
    assert str(exc.value) == (
        f"import task import-snap-1 is {status}: ClientError: Disk validation failed"
    )
    ec2.create_tags.assert_not_called()
    mock_sleep.assert_not_called()


@mock.patch("fleet.tasks._podvm_image_aws.time.sleep")
def test_import_snapshot_fails_when_attempts_are_exhausted(mock_sleep):
    ec2 = mock.MagicMock()
    ec2.import_snapshot.return_value = {"ImportTaskId": "import-snap-1"}
    ec2.describe_import_snapshot_tasks.return_value = _task("active")

    with pytest.raises(PodVMImageError) as exc:
        import_snapshot(ec2, BUCKET, ROLE, CLUSTER, DIGEST, poll_seconds=2, attempts=3)
    assert str(exc.value) == "import task import-snap-1 did not complete within 6 s"
    assert ec2.describe_import_snapshot_tasks.call_count == 3
    assert mock_sleep.call_args_list == [mock.call(2)] * 3
    ec2.create_tags.assert_not_called()


REGISTER_ARGS = {
    "Name": "c1-podvm-0123456789ab",
    "Description": f"{CLUSTER} pod VM image {DIGEST}",
    "Architecture": "x86_64",
    "RootDeviceName": "/dev/xvda",
    "BlockDeviceMappings": [
        {
            "DeviceName": "/dev/xvda",
            "Ebs": {"SnapshotId": "snap-1", "DeleteOnTermination": True},
        }
    ],
    "VirtualizationType": "hvm",
    "EnaSupport": True,
    "BootMode": "uefi",
    "TpmSupport": "v2.0",
    "TagSpecifications": [{"ResourceType": "image", "Tags": TAGS}],
}


def test_register_uses_the_operator_settings():
    ec2 = mock.MagicMock()
    ec2.register_image.return_value = {"ImageId": "ami-1"}
    assert register(ec2, CLUSTER, DIGEST, "snap-1") == "ami-1"
    ec2.register_image.assert_called_once_with(**REGISTER_ARGS)
    ec2.describe_images.assert_not_called()


def test_register_resolves_a_duplicate_name_to_the_tagged_image():
    ec2 = mock.MagicMock()
    ec2.register_image.side_effect = _client_error("InvalidAMIName.Duplicate")
    ec2.describe_images.return_value = {
        "Images": [
            {"ImageId": "ami-untagged"},
            {"ImageId": "ami-other", "Tags": [TAGS[0]]},
            {"ImageId": "ami-1", "Tags": [{"Key": "Name", "Value": "x"}, *TAGS]},
        ]
    }
    assert register(ec2, CLUSTER, DIGEST, "snap-1") == "ami-1"
    ec2.describe_images.assert_called_once_with(
        Owners=["self"],
        Filters=[{"Name": "name", "Values": ["c1-podvm-0123456789ab"]}],
    )


def test_register_fails_on_a_duplicate_name_without_the_tags():
    ec2 = mock.MagicMock()
    ec2.register_image.side_effect = _client_error("InvalidAMIName.Duplicate")
    ec2.describe_images.return_value = {"Images": [{"ImageId": "ami-untagged"}]}
    with pytest.raises(PodVMImageError) as exc:
        register(ec2, CLUSTER, DIGEST, "snap-1")
    assert str(exc.value) == (
        "AMI name c1-podvm-0123456789ab is taken by an image without the tags "
        f"{CLUSTER_LABEL}={CLUSTER} and {PODVM_PAYLOAD_TAG}={DIGEST}"
    )


def test_register_propagates_other_errors():
    ec2 = mock.MagicMock()
    ec2.register_image.side_effect = _client_error("UnauthorizedOperation")
    with pytest.raises(ClientError):
        register(ec2, CLUSTER, DIGEST, "snap-1")
    ec2.describe_images.assert_not_called()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_images_deregisters_and_deletes_snapshots():
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {
        "Images": [
            {
                "ImageId": "ami-1",
                "BlockDeviceMappings": [
                    {"DeviceName": "/dev/xvda", "Ebs": {"SnapshotId": "snap-1"}},
                    {"DeviceName": "/dev/sdb", "VirtualName": "ephemeral0"},
                ],
            },
            {"ImageId": "ami-2"},
        ]
    }
    # snap-1 backs ami-1 and is tagged; snap-2 is a tagged snapshot that no image uses.
    ec2.describe_snapshots.return_value = {
        "Snapshots": [{"SnapshotId": "snap-2"}, {"SnapshotId": "snap-1"}]
    }

    assert delete_images(ec2, CLUSTER) == (2, 2)

    assert ec2.mock_calls == [
        mock.call.describe_images(Owners=["self"], Filters=TEARDOWN_FILTERS),
        mock.call.deregister_image(ImageId="ami-1"),
        mock.call.deregister_image(ImageId="ami-2"),
        mock.call.describe_snapshots(OwnerIds=["self"], Filters=TEARDOWN_FILTERS),
        mock.call.delete_snapshot(SnapshotId="snap-1"),
        mock.call.delete_snapshot(SnapshotId="snap-2"),
    ]


def test_delete_images_with_nothing_to_delete():
    """A persistent volume snapshot has the cluster tag only, so the filter never returns it."""
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {"Images": []}
    ec2.describe_snapshots.return_value = {"Snapshots": []}

    assert delete_images(ec2, CLUSTER) == (0, 0)

    ec2.describe_snapshots.assert_called_once_with(
        OwnerIds=["self"], Filters=TEARDOWN_FILTERS
    )
    ec2.deregister_image.assert_not_called()
    ec2.delete_snapshot.assert_not_called()


def test_delete_images_does_not_count_a_snapshot_that_is_already_gone():
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {"Images": []}
    ec2.describe_snapshots.return_value = {
        "Snapshots": [{"SnapshotId": "snap-1"}, {"SnapshotId": "snap-2"}]
    }
    ec2.delete_snapshot.side_effect = [
        _client_error("InvalidSnapshot.NotFound"),
        None,
    ]
    assert delete_images(ec2, CLUSTER) == (0, 1)


def test_delete_images_propagates_other_errors():
    ec2 = mock.MagicMock()
    ec2.describe_images.return_value = {"Images": []}
    ec2.describe_snapshots.return_value = {"Snapshots": [{"SnapshotId": "snap-1"}]}
    ec2.delete_snapshot.side_effect = _client_error("InvalidSnapshot.InUse")
    with pytest.raises(ClientError):
        delete_images(ec2, CLUSTER)
