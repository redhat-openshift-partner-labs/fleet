from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks._aws_components import COMPONENTS, iam_targets, raw_secret_name
from fleet.tasks.wait_for_aws_component_creds import main

RAW_SECRETS = [raw_secret_name("test-cluster", c.key) for c in COMPONENTS]
TARGETS = iam_targets("test-cluster")


def _ok(stdout=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


def _missing():
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found")


def _item(target, ready=True, message=""):
    kind, name = target.split("/", 1)
    kinds = {
        "user.iam": "User",
        "policy.iam": "Policy",
        "userpolicyattachment.iam": "UserPolicyAttachment",
        "accesskey.iam": "AccessKey",
        "role.iam": "Role",
    }
    return {
        "kind": kinds[kind],
        "metadata": {"name": name},
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True" if ready else "False"},
                {
                    "type": "Synced",
                    "status": "False" if message else "True",
                    "message": message,
                },
            ]
        },
    }


def _resources(items):
    return _ok(json.dumps({"kind": "List", "items": items}))


def _all_ready():
    return _resources([_item(t) for t in TARGETS])


def _argv(timeout=None):
    argv = ["prog", "--cluster-name", "test-cluster"]
    if timeout:
        argv += ["--timeout-seconds", str(timeout)]
    return mock.patch("sys.argv", argv)


def test_raw_secret_names():
    assert RAW_SECRETS == [
        "test-cluster-machine-api-credentials-raw",
        "test-cluster-cco-iam-ro-credentials-raw",
        "test-cluster-image-registry-credentials-raw",
        "test-cluster-ingress-credentials-raw",
        "test-cluster-cncc-credentials-raw",
        "test-cluster-ebs-csi-credentials-raw",
    ]


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_secrets_and_all_resources_ready_immediately(mock_run, mock_sleep):
    mock_run.side_effect = [_ok(), _all_ready()]
    with _argv():
        main()
    mock_sleep.assert_not_called()
    assert mock_run.call_args_list == [
        mock.call(
            ["oc", "get", "secret", *RAW_SECRETS, "-n", "test-cluster", "-o", "name"],
            capture_output=True,
            text=True,
        ),
        mock.call(
            ["oc", "get", *TARGETS, "--ignore-not-found", "-o", "json"],
            capture_output=True,
            text=True,
        ),
    ]


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_waits_for_secrets_before_checking_resources(mock_run, mock_sleep):
    mock_run.side_effect = [_missing(), _ok(), _all_ready()]
    with _argv(timeout=30):
        main()
    mock_sleep.assert_called_once_with(10)
    assert mock_run.call_count == 3


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_waits_until_roles_are_ready(mock_run, mock_sleep):
    """Secrets alone are not enough: the installer needs the BYO node roles to exist."""
    roles_pending = [_item(t, ready=not t.startswith("role.iam/")) for t in TARGETS]
    mock_run.side_effect = [_ok(), _resources(roles_pending), _ok(), _all_ready()]
    with _argv(timeout=30):
        main()
    mock_sleep.assert_called_once_with(10)


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_missing_resource_counts_as_not_ready(mock_run, mock_sleep):
    without_master_role = [_item(t) for t in TARGETS if not t.endswith("-master-role")]
    mock_run.side_effect = [_ok(), _resources(without_master_role), _ok(), _all_ready()]
    with _argv(timeout=30):
        main()
    assert mock_run.call_count == 4


@mock.patch("fleet.tasks.wait_for_aws_component_creds.error")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_timeout_reports_unready_resources_with_synced_message(
    mock_run, mock_sleep, mock_error
):
    denied = "AccessDenied: not authorized to perform: iam:CreateRole"
    items = [
        _item(t, ready=False, message=denied) if t.startswith("role.iam/") else _item(t)
        for t in TARGETS
    ]
    mock_run.side_effect = [
        _ok(),
        _resources(items),  # poll round
        _ok(f"secret/{RAW_SECRETS[0]}\n"),  # timeout report: which secrets exist
        _resources(items),  # timeout report: resource status
    ]
    with _argv(timeout=10):
        with pytest.raises(SystemExit, match="1"):
            main()
    messages = "\n".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "role.iam/test-cluster-master-role" in messages
    assert denied in messages
    assert RAW_SECRETS[1] in messages  # missing secret reported
    assert (
        "user.iam/test-cluster-ingress:" not in messages
    )  # ready resources not reported


@mock.patch("fleet.tasks.wait_for_aws_component_creds.error")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_resource_query_failure_is_not_ready(mock_run, mock_sleep, mock_error):
    failed = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="forbidden"
    )
    mock_run.side_effect = [_ok(), failed, _ok(), failed]
    with _argv(timeout=10):
        with pytest.raises(SystemExit, match="1"):
            main()
    messages = "\n".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert "forbidden" in messages
