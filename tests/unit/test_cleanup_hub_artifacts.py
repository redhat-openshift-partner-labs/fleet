from unittest import mock

import json
import subprocess

import pytest

from fleet.tasks.cleanup_hub_artifacts import main

IAM_RESOURCES = [
    "userpolicyattachment.iam",
    "policy.iam",
    "accesskey.iam",
    "user.iam",
]


def _run(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")


def _run_fail(args, **kwargs):
    return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="error")


def _run_empty_items(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=0, stdout=json.dumps({"items": []}), stderr=""
    )


def _run_has_items(args, **kwargs):
    return subprocess.CompletedProcess(
        args,
        returncode=0,
        stdout=json.dumps({"items": [{"metadata": {"name": "stuck-resource"}}]}),
        stderr="",
    )


def _run_bad_json(args, **kwargs):
    return subprocess.CompletedProcess(
        args, returncode=0, stdout="not valid json", stderr=""
    )


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
            polling round (one oc get per IAM resource type).
        finalizer_results: 4 results for oc patch calls (None if no timeout).
        namespace_result: 1 result for namespace delete.
    """
    effects = []
    effects.extend(pre_delete_results or [_run([])] * 3)
    effects.extend(iam_delete_results or [_run([])] * 4)
    for poll in poll_rounds or [[_run_empty_items([])] * 4]:
        effects.extend(poll)
    if finalizer_results is not None:
        effects.extend(finalizer_results)
    effects.append(namespace_result or _run([]))
    return effects


# ---------------------------------------------------------------------------
# Existing behaviour: pre-delete steps (cert, issuer, secret) and namespace
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
# New: IAM --wait=false flag
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_deletes_use_wait_false(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    for resource in IAM_RESOURCES:
        mock_run.assert_any_call(
            [
                "oc",
                "delete",
                resource,
                "-n",
                "test-cluster",
                "--all",
                "--wait=false",
                "--ignore-not-found=true",
            ],
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# New: polling happy path — resources gone on first poll
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_resources_deleted_on_first_poll(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[[_run_empty_items([])] * 4],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    # 3 pre-deletes + 4 iam deletes + 4 polls + 1 ns delete = 12
    assert mock_run.call_count == 12
    # No finalizer patches should have been called
    for call in mock_run.call_args_list:
        assert "patch" not in call[0][0], "No oc patch calls expected"


# ---------------------------------------------------------------------------
# New: timeout triggers finalizer removal
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_timeout_triggers_finalizer_removal(mock_run, mock_sleep):
    # 30 poll rounds of "still has items" -> timeout -> 4 finalizer patches
    poll_rounds = [[_run_has_items([])] * 4] * 30
    mock_run.side_effect = _make_side_effects(
        poll_rounds=poll_rounds,
        finalizer_results=[_run([])] * 4,
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    # 3 + 4 + (30 * 4) + 4 + 1 = 132
    assert mock_run.call_count == 132
    # Verify oc patch was called for each IAM type
    patch_calls = [
        c for c in mock_run.call_args_list if len(c[0][0]) > 1 and c[0][0][1] == "patch"
    ]
    assert len(patch_calls) == 4


# ---------------------------------------------------------------------------
# New: finalizer patch failure is non-fatal
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_finalizer_patch_failure_non_fatal(mock_run, mock_sleep):
    poll_rounds = [[_run_has_items([])] * 4] * 30
    mock_run.side_effect = _make_side_effects(
        poll_rounds=poll_rounds,
        finalizer_results=[_run_fail([])] * 4,
        namespace_result=_run([]),
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    # Should not raise — namespace delete still attempted and succeeds
    assert mock_run.call_count == 132


# ---------------------------------------------------------------------------
# New: JSON parse error on polling doesn't crash, retries
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_get_json_parse_error_retries(mock_run, mock_sleep):
    # First poll: bad JSON for all 4 resources (treated as "still exists")
    # Second poll: all resources gone
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[
            [_run_bad_json([])] * 4,
            [_run_empty_items([])] * 4,
        ],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    # 3 + 4 + 4 + 4 + 1 = 16
    assert mock_run.call_count == 16
    # No finalizer patches
    patch_calls = [
        c for c in mock_run.call_args_list if len(c[0][0]) > 1 and c[0][0][1] == "patch"
    ]
    assert len(patch_calls) == 0


# ---------------------------------------------------------------------------
# New: oc get returns non-zero (resource type gone) skips without error
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_iam_get_nonzero_exit_treated_as_gone(mock_run, mock_sleep):
    mock_run.side_effect = _make_side_effects(
        poll_rounds=[[_run_fail([])] * 4],
    )
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    # 3 + 4 + 4 + 1 = 12
    assert mock_run.call_count == 12
    patch_calls = [
        c for c in mock_run.call_args_list if len(c[0][0]) > 1 and c[0][0][1] == "patch"
    ]
    assert len(patch_calls) == 0


# ---------------------------------------------------------------------------
# Existing: ordering — polling completes before namespace delete
# ---------------------------------------------------------------------------


@mock.patch("fleet.tasks.cleanup_hub_artifacts.time.sleep")
@mock.patch("fleet.tasks.cleanup_hub_artifacts.subprocess.run")
def test_polling_completes_before_namespace_delete(mock_run, mock_sleep):
    call_order = []

    def track_run(args, **kwargs):
        call_order.append(("run", args))
        if "get" in args and "-o" in args:
            return _run_empty_items(args)
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
