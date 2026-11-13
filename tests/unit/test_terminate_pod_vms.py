from unittest import mock

import binascii
import subprocess

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_components import DiscoveryError
from fleet.tasks.terminate_pod_vms import main
from tests.unit._aws_fixtures import PEER_PODS

MODULE = "fleet.tasks.terminate_pod_vms"
FACTS = ("c1-abcde", "us-east-2", "aws-credentials")
BUCKET = "c1-abcde-podvm-image"
TIER_LOOKUP = [
    "oc",
    "get",
    "managedcluster",
    "c1",
    "--ignore-not-found",
    "-o",
    "jsonpath={.metadata.labels.tier}",
]


def _delete(access_key):
    return [
        "oc",
        "delete",
        "accesskey.iam.aws.upbound.io",
        access_key,
        "--ignore-not-found=true",
        "--wait=true",
        "--timeout=120s",
    ]


def _argv(timeout=None):
    argv = ["prog", "--cluster-name", "c1"]
    if timeout is not None:
        argv += ["--timeout-seconds", str(timeout)]
    return mock.patch("sys.argv", argv)


def _ok(stdout=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


def _fail(stderr):
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=stderr)


@pytest.fixture
def hub():
    """A coco cluster that is installed and has no pod VM and no pod VM image.

    events records the order of the oc calls, the clients and the image and bucket deletion.
    Tests change tier, the delete answer, the credentials, the pod_vm_instances answers and
    deleted, the answer of delete_images.
    """
    events = []
    state = mock.Mock(tier=_ok("coco"), delete=_ok(), events=events, deleted=(0, 0))

    def run(argv, **kwargs):
        assert kwargs == {"capture_output": True, "text": True}
        events.append(("oc", argv))
        return state.tier if argv[1] == "get" else state.delete

    def record(name, result=None):
        def call(*args):
            events.append((name, args))
            return result

        return call

    def delete_images(*args):
        events.append(("delete_images", args))
        return state.deleted

    with (
        mock.patch(f"{MODULE}.subprocess.run", side_effect=run) as oc,
        mock.patch(f"{MODULE}.installed_cluster_facts", return_value=FACTS) as facts,
        mock.patch(
            f"{MODULE}.post_provision_credentials", return_value=[PEER_PODS]
        ) as credentials,
        mock.patch(
            f"{MODULE}.ec2_client", side_effect=record("ec2_client", "ec2")
        ) as ec2_client,
        mock.patch(f"{MODULE}.pod_vm_instances", return_value={}) as instances,
        mock.patch(f"{MODULE}.terminate") as terminate,
        mock.patch(
            f"{MODULE}.delete_images", side_effect=delete_images
        ) as delete_images_mock,
        mock.patch(
            f"{MODULE}.s3_client", side_effect=record("s3_client", "s3")
        ) as s3_client,
        mock.patch(f"{MODULE}.unstage", side_effect=record("unstage")) as unstage,
        mock.patch(f"{MODULE}.time.sleep") as sleep,
        mock.patch(f"{MODULE}.error") as error,
    ):
        state.configure_mock(
            oc=oc,
            facts=facts,
            credentials=credentials,
            ec2_client=ec2_client,
            instances=instances,
            terminate=terminate,
            delete_images=delete_images_mock,
            s3_client=s3_client,
            unstage=unstage,
            sleep=sleep,
            error=error,
        )
        yield state


def _errors(hub):
    return [str(c.args[0]) for c in hub.error.call_args_list]


def _assert_nothing_touched(hub):
    """Only the tier lookup ran: no AccessKey delete, no EC2 call and no S3 call."""
    assert [argv for _, argv in hub.events] == [TIER_LOOKUP]
    hub.credentials.assert_not_called()
    hub.ec2_client.assert_not_called()
    hub.instances.assert_not_called()
    hub.terminate.assert_not_called()
    hub.delete_images.assert_not_called()
    hub.s3_client.assert_not_called()
    hub.unstage.assert_not_called()


# ---------------------------------------------------------------------------
# Clusters without pod VMs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", ["base", "virt", "ai", ""])
def test_other_tiers_and_absent_cluster_return(hub, tier):
    """An absent ManagedCluster has an empty tier: a re-run after its deletion is a no-op."""
    hub.tier = _ok(tier)
    with _argv():
        main()
    _assert_nothing_touched(hub)
    hub.facts.assert_not_called()
    hub.error.assert_not_called()


def test_failed_tier_lookup_exits(hub):
    hub.tier = _fail("Unauthorized\n")
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    _assert_nothing_touched(hub)
    assert _errors(hub) == ["Failed to read the tier label of c1: Unauthorized"]


def test_cluster_not_installed_returns(hub):
    hub.facts.return_value = None
    with _argv():
        main()
    hub.facts.assert_called_once_with("c1")
    _assert_nothing_touched(hub)
    hub.error.assert_not_called()


# ---------------------------------------------------------------------------
# coco: the credential goes first, then the pod VMs
# ---------------------------------------------------------------------------


def test_access_key_is_deleted_before_the_first_ec2_call(hub):
    with _argv():
        main()
    assert hub.events == [
        ("oc", TIER_LOOKUP),
        ("oc", _delete(PEER_PODS.access_key)),
        ("ec2_client", ("c1", "us-east-2", "aws-credentials")),
        ("delete_images", ("ec2", "c1")),
        ("s3_client", ("c1", "us-east-2", "aws-credentials")),
        ("unstage", ("s3", BUCKET)),
    ]
    hub.credentials.assert_called_once_with("c1")
    hub.instances.assert_called_once_with("ec2", "c1", "c1-abcde")
    hub.terminate.assert_not_called()
    hub.sleep.assert_not_called()
    hub.error.assert_not_called()


def test_failed_access_key_delete_exits_before_any_ec2_call(hub):
    hub.delete = _fail("timed out waiting for the condition\n")
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    hub.ec2_client.assert_not_called()
    hub.instances.assert_not_called()
    assert _errors(hub) == [
        f"peer-pods AccessKey {PEER_PODS.access_key} not deleted: "
        "timed out waiting for the condition"
    ]


def test_only_the_peer_pods_access_key_is_deleted(hub):
    other = PEER_PODS._replace(secret="other-secret", access_key="c1-other-access-key")
    hub.credentials.return_value = [other, PEER_PODS]
    with _argv():
        main()
    deletes = [
        argv for name, argv in hub.events if name == "oc" and argv[1] == "delete"
    ]
    assert deletes == [_delete(PEER_PODS.access_key)]


def test_without_a_peer_pods_access_key_pod_vms_are_still_terminated(hub):
    """A re-run after the AccessKey is gone still looks for pod VMs."""
    hub.credentials.return_value = []
    hub.instances.side_effect = [{"i-1": "running"}, {}]
    with _argv():
        main()
    hub.terminate.assert_called_once_with("ec2", ["i-1"])


def test_terminates_once_and_waits_until_gone(hub):
    hub.instances.side_effect = [
        {"i-2": "running", "i-1": "pending"},
        {"i-1": "shutting-down", "i-2": "shutting-down"},
        {},
    ]
    with _argv():
        main()
    hub.terminate.assert_called_once_with("ec2", ["i-1", "i-2"])
    assert [c.args[0] for c in hub.sleep.call_args_list] == [10, 10]
    hub.error.assert_not_called()


def test_pod_vm_that_appears_later_is_terminated(hub):
    """cloud-api-adaptor may launch with a cached credential until IAM drops the key."""
    hub.instances.side_effect = [
        {"i-1": "running"},
        {"i-1": "shutting-down", "i-2": "pending"},
        {"i-2": "shutting-down"},
        {},
    ]
    with _argv():
        main()
    assert hub.terminate.call_args_list == [
        mock.call("ec2", ["i-1"]),
        mock.call("ec2", ["i-2"]),
    ]


def test_instances_left_at_the_timeout_exit(hub):
    hub.instances.return_value = {"i-2": "shutting-down", "i-1": "stopped"}
    with _argv(timeout=20), pytest.raises(SystemExit, match="1"):
        main()
    # Polls at 0, 10 and 20 s
    assert hub.instances.call_count == 3
    assert hub.sleep.call_count == 2
    assert _errors(hub) == [
        "pod VM i-1 is still stopped after 20s",
        "pod VM i-2 is still shutting-down after 20s",
    ]
    hub.delete_images.assert_not_called()
    hub.unstage.assert_not_called()


# ---------------------------------------------------------------------------
# coco: the pod VM image goes after the pod VMs
# ---------------------------------------------------------------------------


def test_images_and_bucket_are_deleted_after_the_pod_vms(hub, capsys):
    answers = iter([{"i-1": "running"}, {"i-1": "shutting-down"}, {}])

    def instances(*args):
        hub.events.append(("pod_vm_instances", args))
        return next(answers)

    hub.instances.side_effect = instances
    hub.deleted = (1, 2)
    with _argv():
        main()
    assert hub.events[2:] == [
        ("ec2_client", ("c1", "us-east-2", "aws-credentials")),
        ("pod_vm_instances", ("ec2", "c1", "c1-abcde")),
        ("pod_vm_instances", ("ec2", "c1", "c1-abcde")),
        ("pod_vm_instances", ("ec2", "c1", "c1-abcde")),
        ("delete_images", ("ec2", "c1")),
        ("s3_client", ("c1", "us-east-2", "aws-credentials")),
        ("unstage", ("s3", BUCKET)),
    ]
    log = capsys.readouterr().err
    assert "Deleted 1 pod VM image(s) and 2 snapshot(s)" in log
    assert f"Staging bucket {BUCKET} is gone" in log
    hub.error.assert_not_called()


def test_nothing_to_delete_is_not_an_error(hub, capsys):
    with _argv():
        main()
    hub.delete_images.assert_called_once_with("ec2", "c1")
    hub.unstage.assert_called_once_with("s3", BUCKET)
    assert "Deleted 0 pod VM image(s) and 0 snapshot(s)" in capsys.readouterr().err
    hub.error.assert_not_called()


def test_image_delete_error_exits_before_the_bucket(hub):
    hub.delete_images.side_effect = ClientError(
        {"Error": {"Code": "InvalidSnapshot.InUse", "Message": "in use"}},
        "DeleteSnapshot",
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    hub.unstage.assert_not_called()
    assert len(_errors(hub)) == 1
    assert "InvalidSnapshot.InUse" in _errors(hub)[0]


def test_bucket_delete_error_exits(hub):
    hub.unstage.side_effect = ClientError(
        {"Error": {"Code": "BucketNotEmpty", "Message": "not empty"}}, "DeleteBucket"
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert len(_errors(hub)) == 1
    assert "BucketNotEmpty" in _errors(hub)[0]


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_discovery_error_exits_before_any_ec2_call(hub):
    hub.credentials.side_effect = DiscoveryError(
        "AccessKey lookup failed for c1: denied"
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    hub.ec2_client.assert_not_called()
    assert _errors(hub) == [
        "Failed to terminate pod VMs: AccessKey lookup failed for c1: denied"
    ]


def test_ec2_error_exits(hub):
    hub.instances.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
        "DescribeInstances",
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert len(_errors(hub)) == 1
    assert "UnauthorizedOperation" in _errors(hub)[0]


def test_failed_cluster_lookup_exits_with_stderr(hub):
    hub.facts.side_effect = subprocess.CalledProcessError(
        1, ["oc", "get", "clusterdeployment"], stderr="Unauthorized\n"
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    hub.credentials.assert_not_called()
    assert len(_errors(hub)) == 1
    assert "Unauthorized" in _errors(hub)[0]


@pytest.mark.parametrize(
    "exc",
    [
        KeyError("aws_access_key_id"),
        binascii.Error("Incorrect padding"),
        BotoCoreError(),
    ],
)
def test_unusable_installer_credential_exits(hub, exc):
    hub.ec2_client.side_effect = exc
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    hub.instances.assert_not_called()
    assert len(_errors(hub)) == 1
    assert _errors(hub)[0].startswith("Failed to terminate pod VMs: ")
