"""IAM follow-up tests at the Kubernetes and AWS boundaries."""

import json
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from fleet.tasks import _iam_cleanup as cleanup


def _item(finalizers=None):
    return {
        "kind": "User",
        "apiVersion": "iam.aws.upbound.io/v1beta1",
        "metadata": {
            "name": "cluster-installer",
            "uid": "uid-1",
            "annotations": {"crossplane.io/external-name": "aws-installer"},
            "deletionTimestamp": "2026-01-01T00:00:00Z",
            "finalizers": finalizers or [cleanup.CROSSPLANE_FINALIZER, "other"],
        },
        "status": {
            "atProvider": {"arn": "arn:aws:iam::123456789012:user/aws-installer"},
            "conditions": [
                {"type": "Synced", "status": "False", "reason": "ReconcileError"}
            ],
        },
    }


def _completed(stdout="", code=0):
    return CompletedProcess([], code, stdout, "Forbidden" if code else "")


def test_snapshot_and_patch_are_scoped_to_an_object(monkeypatch):
    run = Mock(side_effect=[_completed(json.dumps(_item())), _completed()])
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    inventory = cleanup.read_resources(["user.iam/cluster-installer"])
    resource = inventory["user.iam/cluster-installer"]
    cleanup.release_finalizers([resource])
    patch = json.loads(run.call_args.args[0][-1])
    assert patch == [
        {"op": "test", "path": "/metadata/uid", "value": "uid-1"},
        {
            "op": "test",
            "path": "/metadata/deletionTimestamp",
            "value": "2026-01-01T00:00:00Z",
        },
        {
            "op": "test",
            "path": "/metadata/finalizers/0",
            "value": cleanup.CROSSPLANE_FINALIZER,
        },
        {"op": "remove", "path": "/metadata/finalizers/0"},
    ]


def test_report_saved_as_immutable_configmap(monkeypatch):
    run = Mock(return_value=_completed())
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    report = cleanup.build_report("cluster", "run-1", "infra-1", [_item()])
    name = cleanup.save_report(report)
    manifest = json.loads(run.call_args.kwargs["input"])
    assert manifest["metadata"]["name"] == name
    assert manifest["metadata"]["labels"][cleanup.REPORT_LABEL] == "cluster"
    assert manifest["immutable"] is True
    assert json.loads(manifest["data"]["iam.cleanup.json"]) == report
    assert report["items"][0]["state"] == "needs_check"


@pytest.mark.parametrize(
    ("aws_reply", "state"),
    [
        ({}, "confirmed_present"),
        (ClientError({"Error": {"Code": "NoSuchEntity"}}, "GetUser"), None),
        (ClientError({"Error": {"Code": "AccessDenied"}}, "GetUser"), "needs_check"),
    ],
)
def test_report_classifies_aws_observation(monkeypatch, aws_reply, state):
    iam = Mock()
    iam.get_user.side_effect = [aws_reply]
    monkeypatch.setattr(cleanup, "_iam_reader", lambda: (iam, "123456789012"))
    report = cleanup.build_report("cluster", "run-1", "", [_item()])
    assert [item["state"] for item in report["items"]] == ([state] if state else [])
    iam.get_user.assert_called_once_with(UserName="aws-installer")


def test_report_lookup_keeps_latest_observation_per_object(monkeypatch):
    first = cleanup.build_report("cluster", "run-1", "", [_item()])
    second = cleanup.build_report("cluster", "run-2", "", [_item()])
    run = Mock(
        return_value=_completed(
            json.dumps(
                {
                    "items": [
                        {"data": {"iam.cleanup.json": json.dumps(r)}}
                        for r in (first, second)
                    ]
                }
            )
        )
    )
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    report = cleanup.load_report("cluster")
    assert [item["pipeline_run_id"] for item in report["items"]] == ["run-2"]


def test_kubernetes_timeout_is_not_an_empty_lookup(monkeypatch):
    monkeypatch.setattr(
        cleanup.subprocess, "run", Mock(side_effect=TimeoutExpired("oc", 1))
    )
    with pytest.raises(cleanup.CleanupError, match="timed out"):
        cleanup.read_resources(["user.iam/cluster-installer"])


@pytest.mark.parametrize("targets", [[], ["user.iam/missing"]])
def test_missing_resources_return_empty_inventory(monkeypatch, targets):
    run = Mock(return_value=_completed())
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    assert cleanup.read_resources(targets) == {}
    assert run.called == bool(targets)


def test_only_pending_resources_are_patched(monkeypatch):
    resource = _item(["other"])
    run = Mock()
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    cleanup.release_finalizers([resource])
    del resource["metadata"]["deletionTimestamp"]
    with pytest.raises(cleanup.CleanupError, match="Deletion has not been requested"):
        cleanup.release_finalizers([resource])
    run.assert_not_called()


def test_release_tolerates_object_disappearing_during_patch(monkeypatch):
    run = Mock(side_effect=[_completed(code=1), _completed()])
    monkeypatch.setattr(cleanup.subprocess, "run", run)
    cleanup.release_finalizers([_item()])
    assert run.call_args.args[0][1:3] == ["get", "user.iam/cluster-installer"]


@pytest.mark.parametrize("actual_account", ["123456789012", "000000000000", None])
def test_reader_checks_its_account(monkeypatch, actual_account):
    monkeypatch.setenv("FLEET_IAM_AWS_ACCOUNT", "123456789012")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    sts, iam = Mock(), Mock()
    sts.get_caller_identity.return_value = {"Account": actual_account}
    if actual_account is None:
        sts.get_caller_identity.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "GetCallerIdentity"
        )
    monkeypatch.setattr(cleanup.boto3, "client", Mock(side_effect=[sts, iam]))
    client, account = cleanup._iam_reader()
    assert account == "123456789012"
    assert client is (iam if actual_account == account else None)


@pytest.mark.parametrize(
    ("kind", "account", "deadline", "reason"),
    [
        ("Role", "123456789012", float("inf"), "AWSReadSucceeded"),
        ("Policy", "123456789012", float("inf"), "AWSReadSucceeded"),
        ("AccessKey", "123456789012", float("inf"), "AWSResourceLookupUnavailable"),
        ("User", "000000000000", float("inf"), "AWSAccountMismatch"),
        ("User", "123456789012", 0, "AWSReadDeadlineExceeded"),
    ],
)
def test_aws_lookup_states(kind, account, deadline, reason):
    item = {
        "kind": kind,
        "arn": "arn:aws:iam::123456789012:policy/cluster",
        "external_name": "cluster",
    }
    state, actual_reason = cleanup._aws_state(Mock(), item, account, deadline)
    assert actual_reason == reason
    assert state == (
        "confirmed_present" if reason == "AWSReadSucceeded" else "needs_check"
    )


def test_aws_connection_error_needs_check():
    from botocore.exceptions import EndpointConnectionError

    iam = Mock()
    iam.get_user.side_effect = EndpointConnectionError(
        endpoint_url="https://example.com"
    )
    item = {"kind": "User", "arn": "", "external_name": "installer"}
    assert cleanup._aws_state(iam, item, "123456789012", float("inf")) == (
        "needs_check",
        "EndpointConnectionError",
    )


def test_report_lookup_rejects_wrong_cluster(monkeypatch):
    report = {"schema_version": 1, "cluster_name": "other", "items": []}
    output = json.dumps({"items": [{"data": {"iam.cleanup.json": json.dumps(report)}}]})
    monkeypatch.setattr(
        cleanup.subprocess, "run", Mock(return_value=_completed(output))
    )
    with pytest.raises(cleanup.CleanupError, match="Invalid IAM cleanup report"):
        cleanup.load_report("cluster")
