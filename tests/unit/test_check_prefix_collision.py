"""Unit tests for the infra-prefix collision gate."""

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from fleet.tasks.check_prefix_collision import main

MODULE = "fleet.tasks.check_prefix_collision"

# -- helpers ------------------------------------------------------------------


def _oc_json(items):
    return subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout=json.dumps({"items": items}),
        stderr="",
    )


def _oc_empty():
    return subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout=json.dumps({"items": []}),
        stderr="",
    )


def _oc_fail():
    return subprocess.CompletedProcess(
        [],
        returncode=1,
        stdout="",
        stderr="error",
    )


def _item(name, label=None):
    meta = {"name": name}
    if label:
        meta["labels"] = {"openshiftpartnerlabs.com/cluster": label}
    return {"metadata": meta}


def _make_dirs(tmp_path, provision=(), deprovision=()):
    for name in provision:
        (tmp_path / "provision" / name).mkdir(parents=True)
    for name in deprovision:
        (tmp_path / "deprovision" / name).mkdir(parents=True)
    return tmp_path


def _run_gate(cluster, workspace, mock_run):
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            cluster,
            "--workspace-dir",
            str(workspace),
        ],
    ):
        main()


def _run_gate_fail(cluster, workspace, mock_run):
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            cluster,
            "--workspace-dir",
            str(workspace),
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


# -- tests --------------------------------------------------------------------


@mock.patch(f"{MODULE}.subprocess.run")
def test_no_collision_passes(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path, provision=["cluster-alpha"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate("cluster-beta", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_self_match_passes(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path, provision=["my-cluster"])
    mock_run.side_effect = [
        _oc_json([_item("my-cluster")]),
        _oc_json([_item("my-cluster")]),
        _oc_json([_item("my-cluster", label="my-cluster")]),
    ]
    _run_gate("my-cluster", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_exact_name_collision_from_fleet_clusters(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path, provision=["target-cluster", "target-cluster-dup"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate("target-cluster-dup", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_prefix_collision_different_names(mock_run, tmp_path):
    """partner-acme-openshift-1 and partner-acme-openshift-2 share prefix 'partner-acme-openshif'."""
    workspace = _make_dirs(tmp_path, provision=["partner-acme-openshift-1"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_collision_from_clusterdeployment(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path)
    mock_run.side_effect = [
        _oc_json([_item("partner-acme-openshift-1")]),
        _oc_empty(),
        _oc_empty(),
    ]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_collision_from_managedcluster(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path)
    mock_run.side_effect = [
        _oc_empty(),
        _oc_json([_item("partner-acme-openshift-1")]),
        _oc_empty(),
    ]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_collision_from_crossplane_label(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path)
    mock_run.side_effect = [
        _oc_empty(),
        _oc_empty(),
        _oc_json([_item("iam-resource", label="partner-acme-openshift-1")]),
    ]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_archived_cluster_collision(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path, deprovision=["old-cluster-archive"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate_fail("old-cluster", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_normalised_name_collision(mock_run, tmp_path):
    """a--b normalises to a-b; should collide with existing a-b."""
    workspace = _make_dirs(tmp_path, provision=["a-b"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate_fail("a--b", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_hub_api_failure_still_checks_other_sources(mock_run, tmp_path):
    workspace = _make_dirs(tmp_path, provision=["partner-acme-openshift-1"])
    mock_run.side_effect = [_oc_fail(), _oc_fail(), _oc_fail()]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_empty_workspace_no_collision(mock_run, tmp_path):
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate("new-cluster", tmp_path, mock_run)


@mock.patch(f"{MODULE}.subprocess.run")
def test_error_message_contains_details(mock_run, tmp_path, capsys):
    workspace = _make_dirs(tmp_path, provision=["partner-acme-openshift-1"])
    mock_run.side_effect = [_oc_empty(), _oc_empty(), _oc_empty()]
    _run_gate_fail("partner-acme-openshift-2", workspace, mock_run)
    captured = capsys.readouterr()
    assert "partner-acme-openshift-2" in captured.err
    assert "partner-acme-openshift-1" in captured.err
    assert "partner-acme-openshif" in captured.err
    assert "fleet-clusters" in captured.err
