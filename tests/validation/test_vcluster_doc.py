"""Checks that docs/vcluster.md matches the test-vcluster pipeline and its four tools."""

import re

import pytest
import yaml

from tests.validation._markdown import ROOT, table_rows

DOC = ROOT / "docs" / "vcluster.md"
PIPELINES = ROOT / "tekton" / "pipelines"

# CLI entry point -> module that defines its arguments
TOOLS = {
    "fleet-create-test-vcluster": "create_test_vcluster.py",
    "fleet-seed-test-vcluster": "seed_test_vcluster.py",
    "fleet-run-post-provision": "run_post_provision.py",
    "fleet-delete-test-vcluster": "delete_test_vcluster.py",
}


def pipeline_spec(name: str) -> dict:
    text = (PIPELINES / f"{name}.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["spec"]


def body_rows(heading: str) -> dict[str, list[str]]:
    """Rows of the tables of one section, without the header row."""
    rows = table_rows(DOC, heading)
    header = next(iter(rows))
    return {key: cells for key, cells in rows.items() if key != header}


def test_skipped_tasks_are_the_tasks_gated_on_openshift_cluster():
    gated = {
        task["name"]
        for task in pipeline_spec("post-provision")["tasks"]
        if any("openshift-cluster" in when["input"] for when in task.get("when", []))
    }
    assert set(body_rows("## What the test covers")) == gated


def test_parameter_table_holds_the_params_and_defaults_of_the_pipeline():
    params = {p["name"]: p for p in pipeline_spec("test-vcluster")["params"]}
    rows = body_rows("## Run the test")
    assert set(rows) == set(params)

    for name, param in params.items():
        if "default" not in param:
            expected = "Required"
        elif param["default"] == "":
            expected = "Empty"
        else:
            expected = f"`{param['default']}`"
        assert rows[name][1] == expected, f"default of {name}"


def test_task_table_lists_the_tasks_of_the_pipeline():
    spec = pipeline_spec("test-vcluster")
    tasks = [task["name"] for task in spec["tasks"] + spec["finally"]]
    assert list(body_rows("## The pipeline")) == tasks


@pytest.mark.parametrize("tool", TOOLS)
def test_argument_table_holds_the_arguments_of_the_tool(tool):
    source = (ROOT / "fleet" / "tasks" / TOOLS[tool]).read_text(encoding="utf-8")
    arguments = set(re.findall(r'add_argument\(\s*"(--[\w-]+)"', source))
    assert set(body_rows(f"### {tool}")) == arguments
