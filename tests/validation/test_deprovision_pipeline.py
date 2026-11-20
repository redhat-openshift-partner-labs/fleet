"""Validate the IAM report wiring across the deprovision tasks."""

from pathlib import Path

import yaml

TEKTON = Path(__file__).resolve().parents[2] / "tekton"


def _params(task):
    return {param["name"]: param["value"] for param in task["params"]}


def test_iam_cleanup_receives_pipeline_identity_and_infra_id():
    pipeline = yaml.safe_load((TEKTON / "pipelines/deprovision.yaml").read_text())
    tasks = {task["name"]: task for task in pipeline["spec"]["tasks"]}
    cleanup = tasks["cleanup-hub-artifacts"]
    assert cleanup["runAfter"] == ["wait-hive-uninstall"]
    assert _params(cleanup)["pipeline-run-id"] == "$(context.pipelineRun.name)"
    assert (
        _params(cleanup)["infra-id"]
        == "$(tasks.delete-cluster-resources.results.infra-id)"
    )
    assert tasks["verify-deprovision"]["runAfter"] == ["cleanup-hub-artifacts"]
    assert tasks["create-deployment-status"]["runAfter"] == ["verify-deprovision"]
