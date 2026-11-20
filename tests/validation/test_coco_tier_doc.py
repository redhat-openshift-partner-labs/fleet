"""Checks that the failure messages of docs/coco-tier.md are in the coco tier code."""

import re

import yaml

from tests.validation._markdown import ROOT

DOC = ROOT / "docs" / "coco-tier.md"

# Modules that hold the messages of the coco tier tasks.
MODULES = [
    "apply_coco_workloads.py",
    "prepare_podvm_aws.py",
    "build_podvm_image_aws.py",
    "terminate_pod_vms.py",
    "read_cluster_metadata.py",
    "_podvm_aws.py",
    "_podvm_image_aws.py",
    "_aws_binding.py",
    "_aws_components.py",
]


def failure_rows() -> list[tuple[str, str]]:
    """(task, first quoted message) of each row of the failure table."""
    text = DOC.read_text(encoding="utf-8")
    section = text.split("\n## Failure messages\n", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            message = re.search(r"`([^`]+)`", cells[1])[1]
            rows.append((cells[0].strip("`"), message))
    return rows


def anchors(message: str) -> list[str]:
    """Runs of up to three words of the fixed text of a message.

    The text between two <placeholders> is fixed. The document writes the value
    of a constant where the code holds its name, so a whole message is not
    always in the code, but some run of its words is.
    """
    runs = []
    fragments = [f.split() for f in re.split(r"<[^>]*>", message)]
    longest = max(len(words) for words in fragments)
    for words in fragments:
        size = min(3, len(words))
        # A single word proves nothing when the message has a longer fragment.
        if size == 0 or (size < 2 <= longest):
            continue
        runs += [" ".join(words[i : i + size]) for i in range(len(words) - size + 1)]
    return runs


def test_failure_messages_are_in_the_code_of_the_tier():
    sources = "\n".join(
        (ROOT / "fleet" / "tasks" / module).read_text(encoding="utf-8")
        for module in MODULES
    )
    rows = failure_rows()
    assert rows
    for task, message in rows:
        # AWS returns these; the code does not hold their text.
        if message.startswith("An error occurred"):
            continue
        assert any(run in sources for run in anchors(message)), f"{task}: {message}"


def test_failure_table_names_only_tasks_of_the_pipelines():
    tasks = set()
    for path in (ROOT / "tekton" / "pipelines").glob("*.yaml"):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        if definition.get("kind") == "Pipeline":
            tasks |= {task["name"] for task in definition["spec"]["tasks"]}

    named = {task for task, _ in failure_rows()}
    assert named <= tasks, sorted(named - tasks)
