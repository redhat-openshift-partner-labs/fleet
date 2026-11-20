"""Checks that docs/ai-tier.md matches the ai tier tools and workloads/ai/."""

import re

import pytest
import yaml

from fleet.tasks.apply_ai_workloads import _required_operators
from tests.validation._markdown import ROOT, table_rows

DOC = ROOT / "docs" / "ai-tier.md"


def section(heading: str) -> str:
    """Text of one second-level section of the document."""
    text = DOC.read_text(encoding="utf-8")
    return text.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]


def operator_rows() -> list[list[str]]:
    """Cells of the rows of the operator table, without backticks."""
    rows = []
    for line in section("## Operators").splitlines():
        if line.startswith("| `"):
            cells = line.strip().strip("|").split("|")
            rows.append([cell.strip().strip("`") for cell in cells])
    return rows


@pytest.mark.parametrize("version", ["v2", "v3"])
@pytest.mark.parametrize("accelerator", ["none", "nvidia-gpu"])
def test_operator_table_holds_what_the_tool_requires(version, accelerator):
    # Columns: package, channel, catalog, namespace, the clusters it is required for.
    scopes = {"Every `ai` cluster", version, accelerator}
    listed = {
        (package, channel, catalog)
        for package, channel, catalog, _, scope in operator_rows()
        if scope in scopes or f"`{scope}`" in scopes
    }
    assert listed == set(_required_operators(version, accelerator))


def test_operator_table_holds_the_subscriptions_of_the_workloads():
    applied = set()
    for path in (ROOT / "workloads" / "ai").rglob("*subscription.yaml"):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if document and document.get("kind") == "Subscription":
                spec = document["spec"]
                namespace = document["metadata"]["namespace"]
                applied.add((spec["name"], spec["channel"], spec["source"], namespace))

    listed = {tuple(row[:4]) for row in operator_rows()}
    assert listed == applied


def test_failure_messages_are_in_the_module_of_their_task():
    rows = table_rows(DOC, "## Failure messages")
    assert len(rows) > 1
    for key, cells in rows.items():
        if key == "Message":
            continue
        # Column 1 quotes the message, column 2 names the task.
        task = cells[1].strip("`")
        module = ROOT / "fleet" / "tasks" / f"{task.replace('-', '_')}.py"
        # The text before the first placeholder is fixed in the code.
        fixed = key.split("<", 1)[0]
        assert fixed in module.read_text(encoding="utf-8"), f"{task}: {key}"


def test_document_names_only_tasks_of_the_pipelines():
    tasks = set()
    for path in (ROOT / "tekton" / "pipelines").glob("*.yaml"):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        if definition.get("kind") == "Pipeline":
            tasks |= {task["name"] for task in definition["spec"]["tasks"]}

    rows = table_rows(DOC, "## What the pipelines do")
    named = {key for key in rows if key != "Task"}
    assert named and named <= tasks, sorted(named - tasks)
