"""Structural validation of post-provision pipeline tier conditions and ordering."""

from pathlib import Path

import yaml

from fleet.tasks.read_cluster_tier import SUPPORTED_TIERS

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
    assert "coco" in values


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
    assert task.get("runAfter") == ["create-access-paste"]


def test_create_access_paste_runs_only_for_openshift_after_rbac():
    tasks = _load_tasks_by_name()
    task = tasks["create-access-paste"]
    assert _openshift_when_values(task) == ["true"]
    assert task.get("runAfter") == ["configure-spoke-rbac"]


def test_create_access_paste_receives_privatebin_settings():
    tasks = _load_tasks_by_name()
    task = tasks["create-access-paste"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params["privatebin-url"] == "$(tasks.load-config.results.privatebin-url)"
    assert params["expire"] == "$(tasks.load-config.results.privatebin-expire)"


def test_cluster_cronjob_runs_for_every_cluster_after_kubeconfig_save():
    tasks = _load_tasks_by_name()
    task = tasks["create-cluster-cronjob"]
    assert "when" not in task
    assert task.get("runAfter") == ["save-spoke-kubeconfig"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params["timezone"] == "$(params.timezone)"
    assert params["schedule"] == "$(params.schedule)"


# ---------------------------------------------------------------------------
# tier=coco: pod VM lookups on the hub, then the operator on the spoke
# ---------------------------------------------------------------------------

COCO_TASKS = ("prepare-podvm-aws", "build-podvm-image-aws", "apply-coco-workloads")
SOURCE_WORKSPACE = [{"name": "source", "workspace": "shared-workspace"}]


def test_read_cluster_tier_accepts_exactly_the_tiers_the_pipeline_handles():
    """A tier the guard accepts but no task lists would skip every tier task without an error."""
    tasks = _load_tasks_by_name()
    assert sorted(_tier_when_values(tasks["apply-base-workloads"])) == sorted(
        SUPPORTED_TIERS
    )


def test_every_tier_condition_lists_coco_or_belongs_to_another_tier():
    other_tier_tasks = {
        "apply-virt-workloads",
        "add-baremetal-workers",
        "apply-ai-workloads",
        "add-ai-workers",
    }
    for name, task in _load_tasks_by_name().items():
        values = _tier_when_values(task)
        if values and name not in other_tier_tasks:
            assert "coco" in values, name


def test_prepare_podvm_aws_runs_only_for_coco_after_base():
    task = _load_tasks_by_name()["prepare-podvm-aws"]
    assert task["taskRef"] == {"name": "prepare-podvm-aws"}
    assert _tier_when_values(task) == ["coco"]
    assert task.get("runAfter") == ["apply-base-workloads"]
    assert task["workspaces"] == SOURCE_WORKSPACE
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params == {
        "cluster-name": "$(params.cluster-name)",
        "pipeline-image": "$(tasks.load-config.results.pipeline-image)",
    }


def test_build_podvm_image_aws_runs_only_for_coco_after_prepare():
    task = _load_tasks_by_name()["build-podvm-image-aws"]
    assert task["taskRef"] == {"name": "build-podvm-image-aws"}
    assert _tier_when_values(task) == ["coco"]
    assert task.get("runAfter") == ["prepare-podvm-aws"]
    assert task["workspaces"] == SOURCE_WORKSPACE
    # The CLI polls the snapshot import for up to 3600 s after the extraction and the upload
    assert task["timeout"] == "2h"
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params == {
        "cluster-name": "$(params.cluster-name)",
        "pipeline-image": "$(tasks.load-config.results.pipeline-image)",
    }


def test_apply_coco_workloads_runs_only_for_coco_after_the_image_build():
    task = _load_tasks_by_name()["apply-coco-workloads"]
    assert task["taskRef"] == {"name": "apply-coco-workloads"}
    assert _tier_when_values(task) == ["coco"]
    assert task.get("runAfter") == ["build-podvm-image-aws"]
    assert task["workspaces"] == SOURCE_WORKSPACE
    # KataConfig reboots every node; the CLI waits up to 5400 s for it
    assert task["timeout"] == "2h"


def test_apply_coco_workloads_receives_the_network_and_the_image():
    task = _load_tasks_by_name()["apply-coco-workloads"]
    params = {param["name"]: param["value"] for param in task["params"]}
    assert params == {
        "cluster-name": "$(params.cluster-name)",
        "pipeline-image": "$(tasks.load-config.results.pipeline-image)",
        "podvm-instance-type": "$(params.podvm-instance-type)",
        "region": "$(tasks.prepare-podvm-aws.results.region)",
        "vpc-id": "$(tasks.prepare-podvm-aws.results.vpc-id)",
        "subnet-id": "$(tasks.prepare-podvm-aws.results.subnet-id)",
        "sg-ids": "$(tasks.prepare-podvm-aws.results.sg-ids)",
        "ami-id": "$(tasks.build-podvm-image-aws.results.ami-id)",
        "podvm-payload": "$(tasks.build-podvm-image-aws.results.podvm-payload)",
    }


def test_coco_pipeline_params_match_the_task_definitions():
    """Every param the pipeline passes is declared by the Task, and every result it reads exists."""
    tasks_dir = PIPELINE_PATH.parents[1] / "tasks"
    pipeline_tasks = _load_tasks_by_name()
    for name in COCO_TASKS:
        definition = yaml.safe_load((tasks_dir / f"{name}.yaml").read_text())["spec"]
        declared = {param["name"] for param in definition["params"]}
        passed = {param["name"] for param in pipeline_tasks[name]["params"]}
        assert passed == declared, name
        assert [w["name"] for w in definition["workspaces"]] == ["source"], name
    expected_results = {
        "prepare-podvm-aws": {"region", "vpc-id", "subnet-id", "sg-ids"},
        "build-podvm-image-aws": {"ami-id", "podvm-payload"},
    }
    for name, expected in expected_results.items():
        definition = yaml.safe_load((tasks_dir / f"{name}.yaml").read_text())
        results = {result["name"] for result in definition["spec"]["results"]}
        assert results == expected, name


def test_build_podvm_image_aws_has_a_scratch_volume_outside_the_workspace():
    """The disk is larger than the 1Gi workspace; the task extracts it into an emptyDir."""
    tasks_dir = PIPELINE_PATH.parents[1] / "tasks"
    spec = yaml.safe_load((tasks_dir / "build-podvm-image-aws.yaml").read_text())[
        "spec"
    ]
    assert spec["volumes"] == [{"name": "scratch", "emptyDir": {}}]
    (step,) = spec["steps"]
    assert step["volumeMounts"] == [{"name": "scratch", "mountPath": "/scratch"}]
    assert "--work-dir /scratch" in step["script"]


def test_coco_tasks_are_in_the_task_kustomization():
    kustomization = yaml.safe_load(
        (PIPELINE_PATH.parents[1] / "tasks" / "kustomization.yaml").read_text()
    )
    for name in (*COCO_TASKS, "terminate-pod-vms"):
        assert f"{name}.yaml" in kustomization["resources"], name


def test_rbac_waits_for_the_coco_workloads():
    task = _load_tasks_by_name()["configure-spoke-rbac"]
    assert task.get("runAfter") == [
        "apply-base-workloads",
        "add-baremetal-workers",
        "add-ai-workers",
        "apply-coco-workloads",
    ]


def test_coco_selects_base_and_coco_tasks_only():
    tasks = _load_tasks_by_name()
    params = {
        "tier": "coco",
        "ai-accelerator": "nvidia-gpu",
        "openshift-cluster": "true",
    }
    assert _task_runs_for(tasks["apply-base-workloads"], params)
    for name in COCO_TASKS:
        assert _task_runs_for(tasks[name], params), name
    for name in (
        "apply-virt-workloads",
        "add-baremetal-workers",
        "apply-ai-workloads",
        "add-ai-workers",
    ):
        assert not _task_runs_for(tasks[name], params), name


def test_other_tiers_do_not_select_coco_tasks():
    tasks = _load_tasks_by_name()
    for tier in ("base", "virt", "ai"):
        for name in COCO_TASKS:
            assert not _task_runs_for(tasks[name], {"tier": tier}), (tier, name)
