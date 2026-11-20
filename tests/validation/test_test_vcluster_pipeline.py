"""Structural validation of the cleanup of the test-vcluster pipeline."""

import yaml

from tests.validation._markdown import ROOT

PIPELINE = ROOT / "tekton" / "pipelines" / "test-vcluster.yaml"


def _spec() -> dict:
    return yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))["spec"]


def test_cleanup_is_the_finally_task():
    spec = _spec()
    assert [task["name"] for task in spec["finally"]] == ["delete-test-vcluster"]
    assert "delete-test-vcluster" not in {task["name"] for task in spec["tasks"]}


def test_cleanup_needs_no_result_of_an_earlier_task():
    # Tekton skips a finally task that reads the result of a failed or skipped task.
    (cleanup,) = _spec()["finally"]
    values = {param["name"]: param["value"] for param in cleanup["params"]}
    assert not [value for value in values.values() if "$(tasks." in value]
    assert values["pipeline-image"] == "$(params.pipeline-image)"
    assert values["cluster-name"] == "$(params.cluster-name)"
    assert values["namespace"] == "$(params.namespace)"
