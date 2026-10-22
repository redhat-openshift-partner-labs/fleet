"""Structural validation of pre-provision credential handling for scoped AWS clusters."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = ROOT / "tekton" / "pipelines" / "pre-provision.yaml"
METADATA_TASK_PATH = ROOT / "tekton" / "tasks" / "read-cluster-metadata.yaml"
MODE_INPUT = "$(tasks.read-cluster-metadata.results.aws-credentials-mode)"


def _load_tasks_by_name():
    with open(PIPELINE_PATH) as f:
        pipeline = yaml.safe_load(f)
    return {t["name"]: t for t in pipeline["spec"]["tasks"]}


def _mode_when_values(task):
    for condition in task.get("when", []):
        if condition["input"] == MODE_INPUT:
            assert condition["operator"] == "in"
            return condition["values"]
    return []


def test_metadata_task_exposes_platform_and_credentials_mode():
    with open(METADATA_TASK_PATH) as f:
        task = yaml.safe_load(f)
    results = {r["name"] for r in task["spec"]["results"]}
    assert {"platform", "aws-credentials-mode"} <= results
    # Default values are checked by running the script (test_read_cluster_metadata_task.py)


def test_prefix_collision_gate_runs_after_clone():
    task = _load_tasks_by_name()["check-prefix-collision"]
    assert task["runAfter"] == ["git-clone"]
    assert task["workspaces"] == [{"name": "source", "workspace": "shared-workspace"}]


def test_metadata_is_read_after_gate():
    task = _load_tasks_by_name()["read-cluster-metadata"]
    assert task["runAfter"] == ["check-prefix-collision"]
    assert task["workspaces"] == [{"name": "source", "workspace": "shared-workspace"}]


def test_namespace_created_after_gate():
    task = _load_tasks_by_name()["create-cluster-namespace"]
    assert task["runAfter"] == ["check-prefix-collision"]


def test_component_credentials_wait_only_for_scoped_clusters():
    task = _load_tasks_by_name()["wait-for-aws-component-credentials"]
    assert _mode_when_values(task) == ["scoped"]
    assert task["runAfter"] == ["transform-aws-credentials"]


def test_manifests_built_only_for_scoped_clusters_after_wait():
    task = _load_tasks_by_name()["build-aws-credentials-manifests"]
    assert _mode_when_values(task) == ["scoped"]
    assert task["runAfter"] == ["wait-for-aws-component-credentials"]


def test_legacy_credential_tasks_always_run():
    tasks = _load_tasks_by_name()
    for name in ("wait-for-aws-credentials", "transform-aws-credentials"):
        assert _mode_when_values(tasks[name]) == []


def test_validation_waits_for_manifests():
    task = _load_tasks_by_name()["validate-cluster-inputs"]
    assert set(task["runAfter"]) == {
        "transform-aws-credentials",
        "build-aws-credentials-manifests",
    }
