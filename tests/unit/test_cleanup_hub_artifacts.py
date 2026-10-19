from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks._aws_components import COMPONENTS, iam_targets
from fleet.tasks.cleanup_hub_artifacts import main

TARGETS = iam_targets("test-cluster")
PATCH_PAYLOAD = json.dumps({"metadata": {"finalizers": None}})


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")


def _remaining(*names):
    """Poll result listing resources that still exist (oc get -o name)."""
    return subprocess.CompletedProcess(
        [], returncode=0, stdout="".join(f"{n}\n" for n in names), stderr=""
    )


def _make_side_effects(
    pre_delete_results=None,
    iam_delete_result=None,
    poll_rounds=None,
    finalizer_results=None,
    namespace_result=None,
):
    """Build a side_effect list for the full cleanup flow.

    Args:
        pre_delete_results: 3 results for cert, issuer, secret deletes.
        iam_delete_result: 1 result for the bulk IAM --wait=false delete.
        poll_rounds: one result per polling round (bulk ``oc get``); empty
            stdout = all gone.
        finalizer_results: one result per remaining resource patched.
        namespace_result: 1 result for namespace delete.
    """
    effects = []
    effects.extend(pre_delete_results or [_run([])] * 3)
    effects.append(iam_delete_result or _run([]))
    effects.extend(poll_rounds or [_run([])])
    effects.extend(finalizer_results or [])
    effects.append(namespace_result or _run([]))
    return effects


# ---------------------------------------------------------------------------
# IAM targets cover legacy and scoped AWS clusters
# ---------------------------------------------------------------------------


def test_targets_cover_legacy_installer_resources():
    for target in (
        "userpolicyattachment.iam/test-cluster-policy-attachment",
        "policy.iam/test-cluster-openshift4installerpolicy",
        "accesskey.iam/test-cluster-access-key",
        "user.iam/test-cluster-ocp-installer",
    ):
        assert target in TARGETS


def test_targets_cover_scoped_operator_users_and_node_roles():
    for comp in COMPONENTS:
        for target in (
            f"userpolicyattachment.iam/test-cluster-{comp.key}-attachment",
            f"policy.iam/test-cluster-{comp.key}-policy",
            f"accesskey.iam/test-cluster-{comp.key}-access-key",
            f"user.iam/test-cluster-{comp.key}",
        ):
            assert target in TARGETS
    assert "role.iam/test-cluster-master-role" in TARGETS
    assert "role.iam/test-cluster-worker-role" in TARGETS
    assert len(TARGETS) == 4 + 4 * len(COMPONENTS) + 2


def test_attachments_and_keys_deleted_before_users_and_policies():
    first_user = min(i for i, t in enumerate(TARGETS) if t.startswith("user.iam/"))
    first_policy = min(i for i, t in enumerate(TARGETS) if t.startswith("policy.iam/"))
    last_attach = max(
        i for i, t in enumerate(TARGETS) if t.startswith("userpolicyattachment.iam/")
    )
    last_key = max(i for i, t in enumerate(TARGETS) if t.startswith("accesskey.iam/"))
    assert last_attach < first_policy and last_key < first_user


# ---------------------------------------------------------------------------
# Pre-delete steps (cert, issuer, secret) and namespace
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_all_deletions_succeed(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_certificate_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        pre_delete_results=[_run_fail([]), _run([]), _run([])],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_clusterissuer_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        pre_delete_results=[_run([]), _run_fail([]), _run([])],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_crossplane_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        iam_delete_result=_run_fail([]),
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_namespace_deletion_fails_exits_1(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(namespace_result=_run_fail([]))
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_clusterissuer_uses_letsencrypt_prefix(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "clusterissuer",
            "letsencrypt-test-cluster",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_cleanup_certificate_in_openshift_ingress(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "certificate",
            "test-cluster-wildcard-certificate",
            "-n",
            "openshift-ingress",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_cleanup_cert_manager_aws_secret(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        [
            "oc",
            "delete",
            "secret",
            "test-cluster-cert-manager-aws",
            "-n",
            "cert-manager",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# IAM deletes target specific resource names in one call, not --all
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_bulk_delete_uses_specific_names(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        ["oc", "delete", *TARGETS, "--wait=false", "--ignore-not-found=true"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_deletes_do_not_use_all_flag(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    for call in mock_run.call_args_list:
        assert "--all" not in call[0][0], f"--all must not appear: {call[0][0]}"


# ---------------------------------------------------------------------------
# Polling checks specific resource names in one call per round
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_resources_deleted_on_first_poll(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 6
    mock_sleep.assert_not_called()
    for call in mock_run.call_args_list:
        assert "patch" not in call[0][0], "No oc patch calls expected"


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_poll_checks_specific_names(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_run.assert_any_call(
        ["oc", "get", *TARGETS, "--ignore-not-found", "-o", "name"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_resources_deleted_after_retry(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[
            _remaining("user.iam.aws.upbound.io/test-cluster-ingress"),
            _run([]),
        ],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_sleep.assert_called_once_with(2)
    assert mock_run.call_count == 7


# ---------------------------------------------------------------------------
# Timeout triggers finalizer removal only for remaining resources
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_timeout_patches_only_remaining(mock_run, mock_sleep):
    remaining = (
        "user.iam.aws.upbound.io/test-cluster-ingress",
        "role.iam.aws.upbound.io/test-cluster-master-role",
    )
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[_remaining(*remaining)] * 30,
        finalizer_results=[_run([])] * 2,
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 3 + 1 + 30 + 2 + 1
    for name in remaining:
        mock_run.assert_any_call(
            ["oc", "patch", name, "--type=merge", f"-p={PATCH_PAYLOAD}"],
            capture_output=True,
            text=True,
        )


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_poll_errors_patch_all_targets(mock_run, mock_sleep):
    """If oc get keeps failing, nothing is known to be gone: patch every target."""
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[_run_fail([])] * 30,
        finalizer_results=[_run([])] * len(TARGETS),
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    patch_calls = [c for c in mock_run.call_args_list if c[0][0][1] == "patch"]
    assert [c[0][0][2] for c in patch_calls] == TARGETS


# ---------------------------------------------------------------------------
# Finalizer patch failure is non-fatal
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_finalizer_patch_failure_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[_remaining("user.iam.aws.upbound.io/test-cluster-cncc")] * 30,
        finalizer_results=[_run_fail([])],
        namespace_result=_run([]),
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 3 + 1 + 30 + 1 + 1


# ---------------------------------------------------------------------------
# Ordering — polling completes before namespace delete
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_polling_completes_before_namespace_delete(mock_run, mock_sleep):
    call_order = []

    def track_run(args, **kwargs):
        call_order.append(("run", args))
        return _run(args)

    mock_run.side_effect = track_run
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()

    get_indices = [
        i for i, c in enumerate(call_order) if c[0] == "run" and "get" in c[1]
    ]
    ns_idx = next(
        i for i, c in enumerate(call_order) if c[0] == "run" and "namespace" in c[1]
    )
    assert get_indices and all(gi < ns_idx for gi in get_indices)
