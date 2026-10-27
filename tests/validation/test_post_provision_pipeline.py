"""Structural validation of post-provision pipeline tier=virt conditions and ordering."""

from pathlib import Path

import yaml

PIPELINE_PATH = (
    Path(__file__).resolve().parents[2] / "tekton" / "pipelines" / "post-provision.yaml"
)


def _load_tasks_by_name():
    with open(PIPELINE_PATH) as f:
        pipeline = yaml.safe_load(f)
    return {t["name"]: t for t in pipeline["spec"]["tasks"]}


def _tier_when_values(task):
    for condition in task.get("when", []):
        if condition["input"] == "$(params.tier)":
            return condition["values"]
    return []


def _accelerator_when_values(task):
    for condition in task.get("when", []):
        if condition["input"] == "$(params.ai-accelerator)":
            return condition["values"]
    return []


def _task_runs_for(task, params):
    for condition in task.get("when", []):
        param_name = condition["input"].removeprefix("$(params.").removesuffix(")")
        if param_name not in params:
            return False
        if params[param_name] not in condition["values"]:
            return False
    return True


def test_apply_base_workloads_runs_for_base_and_virt():
    tasks = _load_tasks_by_name()
    values = _tier_when_values(tasks["apply-base-workloads"])
    assert "base" in values
    assert "virt" in values
    assert "ai" in values


def test_apply_virt_workloads_runs_only_for_virt_after_base():
    tasks = _load_tasks_by_name()
    task = tasks["apply-virt-workloads"]
    assert _tier_when_values(task) == ["virt"]
    assert task.get("runAfter") == ["apply-base-workloads"]


def test_add_baremetal_workers_runs_only_for_virt_after_virt_workloads():
    tasks = _load_tasks_by_name()
    task = tasks["add-baremetal-workers"]
    assert _tier_when_values(task) == ["virt"]
    assert task.get("runAfter") == ["apply-virt-workloads"]


def test_apply_ai_workloads_runs_only_for_ai_after_base():
    tasks = _load_tasks_by_name()
    task = tasks["apply-ai-workloads"]
    assert _tier_when_values(task) == ["ai"]
    assert task.get("runAfter") == ["apply-base-workloads"]


def test_apply_ai_workloads_receives_accelerator():
    tasks = _load_tasks_by_name()
    task = tasks["apply-ai-workloads"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params["ai-accelerator"] == "$(params.ai-accelerator)"


def test_add_ai_workers_runs_only_for_ai_with_nvidia_gpu():
    tasks = _load_tasks_by_name()
    task = tasks["add-ai-workers"]
    assert _tier_when_values(task) == ["ai"]
    assert _accelerator_when_values(task) == ["nvidia-gpu"]
    assert task.get("runAfter") == ["apply-ai-workloads"]


def test_cpu_only_ai_does_not_select_add_ai_workers():
    tasks = _load_tasks_by_name()
    params = {"tier": "ai", "ai-accelerator": "none"}
    assert _task_runs_for(tasks["apply-ai-workloads"], params)
    assert not _task_runs_for(tasks["add-ai-workers"], params)


def test_nvidia_gpu_ai_selects_add_ai_workers():
    tasks = _load_tasks_by_name()
    params = {"tier": "ai", "ai-accelerator": "nvidia-gpu"}
    assert _task_runs_for(tasks["apply-ai-workloads"], params)
    assert _task_runs_for(tasks["add-ai-workers"], params)


def _openshift_when_values(task):
    for condition in task.get("when", []):
        if condition["input"] == "$(params.openshift-cluster)":
            return condition["values"]
    return []


def test_finalize_spoke_runs_only_for_openshift():
    tasks = _load_tasks_by_name()
    values = _openshift_when_values(tasks["finalize-spoke"])
    assert values == ["true"]


def test_finalize_spoke_runs_after_rbac():
    tasks = _load_tasks_by_name()
    task = tasks["finalize-spoke"]
    assert task.get("runAfter") == ["configure-spoke-rbac"]
