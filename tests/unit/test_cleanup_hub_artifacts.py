from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks.cleanup_hub_artifacts import main

IAM_RESOURCES = {
    "userpolicyattachment.iam": "policy-attachment",
    "policy.iam": "openshift4installerpolicy",
    "accesskey.iam": "access-key",
    "user.iam": "ocp-installer",
}


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")


def _make_side_effects(
    pre_delete_results=None,
    iam_delete_results=None,
    poll_rounds=None,
    finalizer_results=None,
    namespace_result=None,
):
    """Build a side_effect list for the full cleanup flow.

    Args:
        pre_delete_results: 3 results for cert, issuer, secret deletes.
        iam_delete_results: 4 results for IAM --wait=false deletes.
        poll_rounds: list of lists; each inner list is 4 results for one
            polling round (one ``oc get`` per IAM resource type).
            ``_run_fail`` = resource not found (gone);
            ``_run`` = resource still exists.
        finalizer_results: 4 results for oc patch calls (None if no timeout).
        namespace_result: 1 result for namespace delete.
    """
    effects = []
    effects.extend(pre_delete_results or [_run([])] * 3)
    effects.extend(iam_delete_results or [_run([])] * 4)
    for poll in poll_rounds or [[_run_fail([])] * 4]:
        effects.extend(poll)
    if finalizer_results is not None:
        effects.extend(finalizer_results)
    effects.append(namespace_result or _run([]))
    return effects


# ---------------------------------------------------------------------------
# Pre-delete steps (cert, issuer, secret) and namespace
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_all_deletions_succeed(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 12


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_certificate_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        pre_delete_results=[_run_fail([]), _run([]), _run([])],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 12


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_clusterissuer_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        pre_delete_results=[_run([]), _run_fail([]), _run([])],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 12


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_crossplane_deletion_non_fatal(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        iam_delete_results=[_run_fail([])] * 4,
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 12


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
# IAM deletes target specific resource names, not --all
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_deletes_use_specific_names(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    for resource_type, suffix in IAM_RESOURCES.items():
        mock_run.assert_any_call(
            [
                "oc",
                "delete",
                resource_type,
                f"test-cluster-{suffix}",
                "--wait=false",
                "--ignore-not-found=true",
            ],
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
# Polling checks specific resource names
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_resources_deleted_on_first_poll(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[[_run_fail([])] * 4],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 12
    for call in mock_run.call_args_list:
        assert "patch" not in call[0][0], "No oc patch calls expected"


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_poll_checks_specific_names(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[[_run_fail([])] * 4],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    for resource_type, suffix in IAM_RESOURCES.items():
        mock_run.assert_any_call(
            [
                "oc",
                "get",
                resource_type,
                f"test-cluster-{suffix}",
            ],
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# Timeout triggers finalizer removal by specific name
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_timeout_triggers_finalizer_removal(mock_run, mock_sleep):
    poll_rounds = [[_run([])] * 4] * 30
    mock_run.side_effect = _make_side_effects(
        poll_rounds=poll_rounds,
        finalizer_results=[_run([])] * 4,
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 132
    patch_calls = [
        c for c in mock_run.call_args_list if len(c[0][0]) > 1 and c[0][0][1] == "patch"
    ]
    assert len(patch_calls) == 4


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_finalizer_patches_use_specific_names(mock_run, mock_sleep):
    patch_payload = json.dumps({"metadata": {"finalizers": None}})
    poll_rounds = [[_run([])] * 4] * 30
    mock_run.side_effect = _make_side_effects(
        poll_rounds=poll_rounds,
        finalizer_results=[_run([])] * 4,
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    for resource_type, suffix in IAM_RESOURCES.items():
        mock_run.assert_any_call(
            [
                "oc",
                "patch",
                resource_type,
                f"test-cluster-{suffix}",
                "--type=merge",
                f"-p={patch_payload}",
            ],
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# Finalizer patch failure is non-fatal
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_finalizer_patch_failure_non_fatal(mock_run, mock_sleep):
    poll_rounds = [[_run([])] * 4] * 30
    mock_run.side_effect = _make_side_effects(
        poll_rounds=poll_rounds,
        finalizer_results=[_run_fail([])] * 4,
        namespace_result=_run([]),
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    assert mock_run.call_count == 132


# ---------------------------------------------------------------------------
# Ordering — polling completes before namespace delete
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_polling_completes_before_namespace_delete(mock_run, mock_sleep):
    call_order = []

    def track_run(args, **kwargs):
        call_order.append(("run", args))
        if "get" in args:
            return _run_fail(args)
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
    assert all(gi < ns_idx for gi in get_indices)
