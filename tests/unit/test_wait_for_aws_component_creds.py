from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks._aws_components import DiscoveryError
from fleet.tasks.wait_for_aws_component_creds import main
from tests.unit._aws_fixtures import OPERATORS, PEER_PODS, iam_targets_for

# The wait covers every discovered credential, the post-provision one included
DISCOVERED = OPERATORS + [PEER_PODS]
RAW_SECRETS = [c.raw_secret for c in DISCOVERED]
TARGETS = iam_targets_for("test-cluster", DISCOVERED)


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


@pytest.fixture(autouse=True)
def discovery():
    """Every main() test sees DISCOVERED and their IAM resources from discovery.

    The task imports both functions by name, so the patch goes on the task module. The oc
    sequences below therefore hold only the Secret and resource polls, as before.
    """
    with (
        mock.patch(
            "fleet.tasks.wait_for_aws_component_creds.discover_components",
            return_value=DISCOVERED,
        ) as discover,
        mock.patch(
            "fleet.tasks.wait_for_aws_component_creds.all_iam_targets",
            return_value=TARGETS,
        ),
    ):
        yield discover


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
def test_waits_for_the_post_provision_raw_secret(mock_run, mock_sleep):
    """The peer-pods raw Secret must exist before the install starts (post-provision reads it)."""
    mock_run.side_effect = [_ok(), _all_ready()]
    with _argv():
        main()
    poll = mock_run.call_args_list[0].args[0]
    assert poll[:3] == ["oc", "get", "secret"]
    assert "test-cluster-peer-pods-credentials-raw" in poll


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


@mock.patch("fleet.tasks.wait_for_aws_component_creds.info")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_discovery_runs_once_and_reports_counts(
    mock_run, mock_sleep, mock_info, discovery
):
    mock_run.side_effect = [_ok(), _all_ready()]
    with _argv():
        main()
    discovery.assert_called_once_with("test-cluster")
    logged = [str(c.args[0]) for c in mock_info.call_args_list]
    assert f"  secrets={len(RAW_SECRETS)} iam-resources={len(TARGETS)}" in logged


@mock.patch("fleet.tasks.wait_for_aws_component_creds.error")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_discovery_failure_exits_before_polling(
    mock_run, mock_sleep, mock_error, discovery
):
    """An overlay without annotations fails at once; re-running the pipeline is the recovery."""
    message = "AccessKey lookup failed for test-cluster: denied"
    discovery.side_effect = DiscoveryError(message)
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_sleep.assert_not_called()
    mock_run.assert_not_called()
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [message]
