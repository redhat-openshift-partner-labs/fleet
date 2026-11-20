"""Checks that docs/architecture.md matches the repository."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
DOC = ROOT / "docs" / "architecture.md"
PIPELINES = ["pre-provision", "provision", "post-provision", "deprovision"]

# Target of a markdown link or image: [text](target) or ![alt](target)
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
IMAGE_TARGET = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def test_relative_links_resolve():
    text = DOC.read_text(encoding="utf-8")
    targets = [
        target
        for target in LINK_TARGET.findall(text)
        if not target.startswith(EXTERNAL_PREFIXES)
    ]
    assert targets

    # Drop a trailing #anchor before the path check.
    missing = [t for t in targets if not (DOC.parent / t.split("#", 1)[0]).exists()]
    assert not missing, f"architecture.md links to missing paths: {missing}"


def test_every_diagram_is_an_svg_with_a_link_to_its_mermaid_source():
    text = DOC.read_text(encoding="utf-8")
    images = IMAGE_TARGET.findall(text)
    # The architecture diagram, and a flowchart and a sequence per pipeline.
    assert len(images) == 1 + 2 * len(PIPELINES)

    links = set(LINK_TARGET.findall(text))
    for image in images:
        assert image.endswith(".svg"), image
        source = image.removesuffix(".svg") + ".mermaid"
        assert source in links, f"architecture.md has no link to {source}"

    # GitHub renders a mermaid block; the SVG is the inline form.
    assert "```mermaid" not in text


@pytest.mark.parametrize("name", PIPELINES)
def test_task_table_lists_the_tasks_of_the_pipeline(name):
    text = DOC.read_text(encoding="utf-8")
    sections = re.split(r"^### ", text, flags=re.MULTILINE)
    section = [s for s in sections if s.splitlines()[0].strip() == name]
    assert len(section) == 1, f"architecture.md needs one '### {name}' section"

    # A task row starts with the task name in backticks.
    listed = re.findall(r"^\| `([\w-]+)` \|", section[0], flags=re.MULTILINE)
    path = ROOT / "tekton" / "pipelines" / f"{name}.yaml"
    tasks = yaml.safe_load(path.read_text(encoding="utf-8"))["spec"]["tasks"]
    assert sorted(listed) == sorted(task["name"] for task in tasks)
