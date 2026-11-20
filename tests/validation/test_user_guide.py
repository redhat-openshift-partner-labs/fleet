"""Checks that docs/user-guide.md matches the repository and the other documents."""

import re

import pytest
import yaml

from tests.validation._markdown import ROOT, links

GUIDE = ROOT / "docs" / "user-guide.md"
PIPELINES = ["pre-provision", "provision", "post-provision", "deprovision"]


def pipeline_task_names() -> set[str]:
    names = set()
    for path in (ROOT / "tekton" / "pipelines").glob("*.yaml"):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        # The directory also holds its kustomization.yaml.
        if definition.get("kind") == "Pipeline":
            names |= {task["name"] for task in definition["spec"]["tasks"]}
    return names


@pytest.mark.parametrize("name", PIPELINES)
def test_guide_links_to_the_task_table_of_each_pipeline(name):
    assert f"architecture.md#{name}" in links(GUIDE)


def test_troubleshooting_names_only_tasks_of_the_pipelines():
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split("\n## Troubleshooting\n", 1)[1].split("\n## ", 1)[0]
    # A troubleshooting row starts with the task name in backticks.
    named = re.findall(r"^\| `([\w-]+)` \|", section, flags=re.MULTILINE)
    assert named
    unknown = sorted(set(named) - pipeline_task_names())
    assert not unknown, f"user-guide.md names tasks that no pipeline has: {unknown}"


def test_crossplane_api_groups_are_the_ones_the_tasks_use():
    text = GUIDE.read_text(encoding="utf-8")
    # Resource names such as accesskeys.iam.aws.upbound.io in oc commands.
    groups = set(re.findall(r"\b[a-z]+\.(iam\.aws\.[a-z.]+[a-z])", text))
    assert groups

    sources = list((ROOT / "fleet" / "tasks").glob("*.py"))
    sources += list((ROOT / "hub-config" / "crossplane").rglob("*.yaml"))
    used = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    unknown = sorted(group for group in groups if group not in used)
    assert not unknown, f"user-guide.md uses API groups no task uses: {unknown}"
