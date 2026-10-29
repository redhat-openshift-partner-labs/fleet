"""Structural validation of post-install AWS credential scoping in the provision pipeline."""

from pathlib import Path

import yaml

PIPELINE_PATH = (
    Path(__file__).resolve().parents[2] / "tekton" / "pipelines" / "provision.yaml"
)
MODE_INPUT = "$(tasks.read-cluster-metadata.results.aws-credentials-mode)"
AI_ACCELERATOR_INPUT = "$(tasks.read-cluster-metadata.results.ai-accelerator)"


def _load_tasks_by_name():
    with open(PIPELINE_PATH) as f:
        pipeline = yaml.safe_load(f)
    return {t["name"]: t for t in pipeline["spec"]["tasks"]}


def test_scope_runs_only_for_scoped_clusters_after_install():
    task = _load_tasks_by_name()["scope-aws-credentials"]
    assert task["when"] == [
        {"input": MODE_INPUT, "operator": "in", "values": ["scoped"]}
    ]
    # infraID exists once Hive reports the install; metadata provides the mode
    assert set(task["runAfter"]) == {"wait-for-hive-ready", "read-cluster-metadata"}


def test_partner_handoff_waits_for_scoping():
    task = _load_tasks_by_name()["trigger-post-provision"]
    assert "scope-aws-credentials" in task["runAfter"]


def test_post_provision_receives_ai_accelerator():
    task = _load_tasks_by_name()["trigger-post-provision"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params["ai-accelerator"] == AI_ACCELERATOR_INPUT


def test_post_provision_receives_cronjob_settings():
    task = _load_tasks_by_name()["trigger-post-provision"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params["timezone"] == ("$(tasks.read-cluster-metadata.results.timezone)")
    assert params["schedule"] == ("$(tasks.read-cluster-metadata.results.schedule)")


def test_every_task_param_is_a_name_value_mapping():
    for name, task in _load_tasks_by_name().items():
        for param in task.get("params", []):
            assert isinstance(param, dict) and {"name", "value"} <= set(param), name
