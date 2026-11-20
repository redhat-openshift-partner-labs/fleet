"""Checks that docs/user-guide.md matches the repository and the other documents."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
GUIDE = ROOT / "docs" / "user-guide.md"
PIPELINES = ["pre-provision", "provision", "post-provision", "deprovision"]

# Documents whose links to a heading are checked against the target document.
ANCHOR_CHECKED = ["docs/user-guide.md", "docs/architecture.md"]

# Target of a markdown link or image: [text](target) or ![alt](target)
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:")


def headings(path: Path) -> set[str]:
    """Anchors of the headings of a markdown file, as GitHub derives them."""
    anchors = set()
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            # GitHub drops punctuation and turns each space into a hyphen.
            anchors.add(re.sub(r"[^\w\- ]", "", title).replace(" ", "-"))
    return anchors


def links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [t for t in LINK_TARGET.findall(text) if not t.startswith(EXTERNAL_PREFIXES)]


def pipeline_task_names() -> set[str]:
    names = set()
    for path in (ROOT / "tekton" / "pipelines").glob("*.yaml"):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        # The directory also holds its kustomization.yaml.
        if definition.get("kind") == "Pipeline":
            names |= {task["name"] for task in definition["spec"]["tasks"]}
    return names


@pytest.mark.parametrize("document", ANCHOR_CHECKED)
def test_links_and_anchors_resolve(document):
    source = ROOT / document
    targets = links(source)
    assert targets

    for target in targets:
        path, _, anchor = target.partition("#")
        file = source.parent / path if path else source
        assert file.exists(), f"{document} links to the missing path {path}"
        if anchor and file.suffix == ".md":
            assert anchor in headings(file), f"{document}: no heading for {target}"


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
