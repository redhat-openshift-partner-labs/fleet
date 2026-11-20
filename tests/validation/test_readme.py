"""Checks that README.md matches the repository."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
README = ROOT / "README.md"

# Target of a markdown link or image: [text](target) or ![alt](target)
LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def test_pipeline_task_counts_match_definitions():
    lines = README.read_text(encoding="utf-8").splitlines()
    checked = 0

    for path in sorted((ROOT / "tekton" / "pipelines").glob("*.yaml")):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        if definition.get("kind") != "Pipeline":
            continue

        # The pipelines table has one row per pipeline; the row links the
        # definition file and its last cell is the task count.
        link = f"(tekton/pipelines/{path.name})"
        rows = [line for line in lines if line.startswith("|") and link in line]
        assert len(rows) == 1, f"README.md needs one table row linking {path.name}"

        cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
        expected = str(len(definition["spec"]["tasks"]))
        assert cells[-1] == expected, f"{path.name}: README.md states {cells[-1]}"
        checked += 1

    assert checked > 0


def test_relative_links_resolve():
    text = README.read_text(encoding="utf-8")
    targets = [
        target
        for target in LINK_TARGET.findall(text)
        if not target.startswith(EXTERNAL_PREFIXES)
    ]
    assert targets

    # Drop a trailing #anchor before the path check.
    missing = [t for t in targets if not (ROOT / t.split("#", 1)[0]).exists()]
    assert not missing, f"README.md links to missing paths: {missing}"
