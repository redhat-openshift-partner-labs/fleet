import base64
import binascii
import json
import os
import stat
import subprocess
from unittest import mock

import pytest
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._podvm_image_aws import PodVMImageError
from fleet.tasks.build_podvm_image_aws import main

MODULE = "fleet.tasks.build_podvm_image_aws"
KUBECONFIG = "/workspace/source/kubeconfig"
FACTS = ("c1-abcde", "us-east-2", "aws-credentials")
DIGEST = "sha256:" + "0123456789ab" + "c" * 52
IMAGE = (
    f"registry.redhat.io/openshift-sandboxed-containers/osc-dm-verity-image@{DIGEST}"
)
RELATED = ["registry.redhat.io/openshift-sandboxed-containers/operator@sha256:1", IMAGE]
BUCKET = "c1-abcde-podvm-image"
PULL_SECRET = '{"auths":{"registry.redhat.io":{"auth":"dG9wLXNlY3JldA=="}}}'


def _argv(work_dir):
    return mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "c1",
            "--spoke-kubeconfig",
            KUBECONFIG,
            "--work-dir",
            str(work_dir),
        ],
    )


def _secret(data):
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=json.dumps({"data": data}), stderr=""
    )


def _client_error(code, operation):
    return ClientError({"Error": {"Code": code, "Message": "denied"}}, operation)


@pytest.fixture(autouse=True)
def helpers(tmp_path):
    """Every lookup, EC2, S3 and tool helper is replaced; the pull secret read is the only oc call.

    extract_disk and to_raw leave the files the real ones leave, and extract_disk records the
    registry config file as it is during the extraction.
    """
    seen = {}

    def _extract(_image, registry_config, work_dir):
        seen["mode"] = stat.S_IMODE(os.stat(registry_config).st_mode)
        with open(registry_config, encoding="utf-8") as handle:
            seen["content"] = handle.read()
        os.makedirs(os.path.join(work_dir, "image"))
        disk = os.path.join(work_dir, "image", "podvm.qcow2")
        with open(disk, "wb") as handle:
            handle.write(b"qcow2")
        return disk

    def _to_raw(_disk, work_dir):
        raw = os.path.join(work_dir, "podvm.raw")
        with open(raw, "wb") as handle:
            handle.write(b"raw")
        return raw

    encoded = base64.b64encode(PULL_SECRET.encode()).decode()
    with (
        mock.patch(f"{MODULE}.cluster_facts", return_value=FACTS) as cluster_facts,
        mock.patch(f"{MODULE}.ec2_client") as ec2_client,
        mock.patch(f"{MODULE}.s3_client") as s3_client,
        mock.patch(
            f"{MODULE}.channel_related_images", return_value=RELATED
        ) as related_images,
        mock.patch(f"{MODULE}.find_image", return_value=None) as find_image,
        mock.patch(f"{MODULE}.find_snapshot", return_value=None) as find_snapshot,
        mock.patch(f"{MODULE}.extract_disk", side_effect=_extract) as extract_disk,
        mock.patch(f"{MODULE}.to_raw", side_effect=_to_raw) as to_raw,
        mock.patch(f"{MODULE}.stage") as stage,
        mock.patch(f"{MODULE}.unstage") as unstage,
        mock.patch(f"{MODULE}.import_snapshot", return_value="snap-1") as importer,
        mock.patch(f"{MODULE}.register", return_value="ami-1") as register,
        mock.patch(
            f"{MODULE}.subprocess.run",
            return_value=_secret({".dockerconfigjson": encoded}),
        ) as run,
    ):
        calls = mock.Mock()
        for name, helper in (
            ("find_image", find_image),
            ("find_snapshot", find_snapshot),
            ("extract_disk", extract_disk),
            ("to_raw", to_raw),
            ("stage", stage),
            ("import_snapshot", importer),
            ("unstage", unstage),
            ("register", register),
        ):
            calls.attach_mock(helper, name)
        yield mock.Mock(
            cluster_facts=cluster_facts,
            ec2_client=ec2_client,
            s3_client=s3_client,
            related_images=related_images,
            find_image=find_image,
            find_snapshot=find_snapshot,
            extract_disk=extract_disk,
            to_raw=to_raw,
            stage=stage,
            unstage=unstage,
            import_snapshot=importer,
            register=register,
            run=run,
            calls=calls,
            seen=seen,
            work_dir=tmp_path,
        )


def _run(helpers):
    with _argv(helpers.work_dir):
        main()


def _assert_fails(helpers, capsys, message):
    """Exit 1, one error line containing message, nothing on stdout."""
    with mock.patch(f"{MODULE}.error") as mock_error:
        with _argv(helpers.work_dir), pytest.raises(SystemExit, match="1"):
            main()
    assert len(mock_error.call_args_list) == 1
    assert message in str(mock_error.call_args.args[0])
    assert capsys.readouterr().out == ""


def _assert_no_build(helpers):
    helpers.run.assert_not_called()
    helpers.extract_disk.assert_not_called()
    helpers.stage.assert_not_called()
    helpers.import_snapshot.assert_not_called()
    helpers.unstage.assert_not_called()
    assert os.listdir(helpers.work_dir) == []


def test_reuses_an_image_of_the_digest(helpers, capsys):
    helpers.find_image.return_value = "ami-0"

    _run(helpers)

    assert json.loads(capsys.readouterr().out) == {
        "ami-id": "ami-0",
        "podvm-payload": DIGEST,
    }
    ec2 = helpers.ec2_client.return_value
    helpers.cluster_facts.assert_called_once_with("c1")
    helpers.ec2_client.assert_called_once_with("c1", "us-east-2", "aws-credentials")
    helpers.s3_client.assert_called_once_with("c1", "us-east-2", "aws-credentials")
    helpers.related_images.assert_called_once_with(
        "sandboxed-containers-operator", "stable", "redhat-operators", KUBECONFIG
    )
    helpers.find_image.assert_called_once_with(ec2, "c1", DIGEST)
    helpers.find_snapshot.assert_not_called()
    helpers.register.assert_not_called()
    _assert_no_build(helpers)


def test_registers_a_snapshot_of_the_digest(helpers, capsys):
    helpers.find_snapshot.return_value = "snap-0"

    _run(helpers)

    assert json.loads(capsys.readouterr().out) == {
        "ami-id": "ami-1",
        "podvm-payload": DIGEST,
    }
    ec2 = helpers.ec2_client.return_value
    helpers.find_snapshot.assert_called_once_with(ec2, "c1", DIGEST)
    helpers.register.assert_called_once_with(ec2, "c1", DIGEST, "snap-0")
    _assert_no_build(helpers)


def test_builds_in_order_and_cleans_up(helpers, capsys):
    _run(helpers)

    assert json.loads(capsys.readouterr().out) == {
        "ami-id": "ami-1",
        "podvm-payload": DIGEST,
    }
    ec2 = helpers.ec2_client.return_value
    s3 = helpers.s3_client.return_value
    work_dir = str(helpers.work_dir)
    registry_config = os.path.join(work_dir, "pull-secret.json")
    disk = os.path.join(work_dir, "image", "podvm.qcow2")
    raw = os.path.join(work_dir, "podvm.raw")
    assert helpers.calls.mock_calls == [
        mock.call.find_image(ec2, "c1", DIGEST),
        mock.call.find_snapshot(ec2, "c1", DIGEST),
        mock.call.extract_disk(IMAGE, registry_config, work_dir),
        mock.call.to_raw(disk, work_dir),
        mock.call.stage(s3, BUCKET, "us-east-2", raw),
        mock.call.import_snapshot(ec2, BUCKET, "c1-vmimport-role", "c1", DIGEST),
        mock.call.unstage(s3, BUCKET),
        mock.call.register(ec2, "c1", DIGEST, "snap-1"),
    ]
    helpers.run.assert_called_once_with(
        [
            "oc",
            "get",
            "secret",
            "pull-secret",
            "-n",
            "openshift-config",
            "-o",
            "json",
            f"--kubeconfig={KUBECONFIG}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # The disk files and the pull secret file are gone.
    assert os.listdir(work_dir) == []


def test_pull_secret_file_is_private_and_removed_and_never_logged(helpers, capsys):
    _run(helpers)

    assert helpers.seen == {"mode": 0o600, "content": PULL_SECRET}
    assert not os.path.exists(os.path.join(helpers.work_dir, "pull-secret.json"))
    captured = capsys.readouterr()
    for text in (captured.out, captured.err):
        assert PULL_SECRET not in text
        assert "dG9wLXNlY3JldA==" not in text


def test_pull_secret_file_replaces_a_leftover_file(helpers):
    leftover = helpers.work_dir / "pull-secret.json"
    leftover.write_text("stale")
    leftover.chmod(0o644)

    _run(helpers)

    assert helpers.seen == {"mode": 0o600, "content": PULL_SECRET}
    assert not leftover.exists()


def test_pull_secret_file_is_removed_when_the_extraction_fails(helpers, capsys):
    def _fail(_image, registry_config, _work_dir):
        assert os.path.exists(registry_config)
        raise PodVMImageError("oc image extract failed: unauthorized")

    helpers.extract_disk.side_effect = _fail

    _assert_fails(helpers, capsys, "oc image extract failed: unauthorized")

    assert os.listdir(helpers.work_dir) == []
    helpers.stage.assert_not_called()
    helpers.unstage.assert_called_once_with(helpers.s3_client.return_value, BUCKET)
    helpers.register.assert_not_called()


def test_failed_import_cleans_up_and_exits(helpers, capsys):
    helpers.import_snapshot.side_effect = PodVMImageError(
        "import task import-snap-1 is deleted: ClientError: Disk validation failed"
    )

    _assert_fails(helpers, capsys, "import task import-snap-1 is deleted")

    helpers.unstage.assert_called_once_with(helpers.s3_client.return_value, BUCKET)
    helpers.register.assert_not_called()
    assert os.listdir(helpers.work_dir) == []


def test_failed_cleanup_is_a_warning_after_a_successful_import(helpers, capsys):
    helpers.unstage.side_effect = _client_error("BucketNotEmpty", "DeleteBucket")

    with mock.patch(f"{MODULE}.warn") as mock_warn:
        _run(helpers)

    assert json.loads(capsys.readouterr().out)["ami-id"] == "ami-1"
    mock_warn.assert_called_once()
    assert BUCKET in mock_warn.call_args.args[0]
    assert "BucketNotEmpty" in mock_warn.call_args.args[0]
    helpers.register.assert_called_once()


def test_failed_cleanup_does_not_hide_the_build_error(helpers, capsys):
    helpers.stage.side_effect = S3UploadFailedError("Failed to upload podvm.raw")
    helpers.unstage.side_effect = BotoCoreError()

    with mock.patch(f"{MODULE}.warn") as mock_warn:
        _assert_fails(helpers, capsys, "Failed to upload podvm.raw")

    mock_warn.assert_called_once()
    helpers.import_snapshot.assert_not_called()


def test_pull_secret_read_failure_exits_with_stderr(helpers, capsys):
    helpers.run.side_effect = subprocess.CalledProcessError(
        1, ["oc", "get", "secret"], stderr="Unable to connect to the server\n"
    )
    _assert_fails(helpers, capsys, "Unable to connect to the server")
    helpers.extract_disk.assert_not_called()


def test_pull_secret_without_docker_config_exits(helpers, capsys):
    helpers.run.return_value = _secret({"other": "eA=="})
    _assert_fails(helpers, capsys, ".dockerconfigjson")
    helpers.extract_disk.assert_not_called()
    assert os.listdir(helpers.work_dir) == []


def test_catalog_failure_exits_before_any_lookup(helpers, capsys):
    helpers.related_images.side_effect = ValueError(
        "sandboxed-containers-operator is not available from any catalog"
    )
    _assert_fails(helpers, capsys, "is not available from any catalog")
    helpers.find_image.assert_not_called()


def test_missing_disk_image_exits(helpers, capsys):
    helpers.related_images.return_value = [RELATED[0]]
    _assert_fails(helpers, capsys, "no related image of repository")
    helpers.find_image.assert_not_called()


def test_ec2_error_exits(helpers, capsys):
    helpers.find_image.side_effect = _client_error(
        "UnauthorizedOperation", "DescribeImages"
    )
    _assert_fails(helpers, capsys, "UnauthorizedOperation")
    helpers.find_snapshot.assert_not_called()


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("ClusterDeployment c1 has no infraID (not installed?)"),
        KeyError("aws_access_key_id"),
        binascii.Error("Incorrect padding"),
        BotoCoreError(),
        OSError("No space left on device"),
    ],
)
def test_hub_lookup_failure_exits(helpers, capsys, exc):
    helpers.cluster_facts.side_effect = exc
    _assert_fails(helpers, capsys, "Failed to build the pod VM image")
    helpers.related_images.assert_not_called()
