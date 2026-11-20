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


# Documents that open with a purpose sentence. The documentation index of
# README.md holds the same text.
PURPOSE_DOCS = ["docs/architecture.md", "docs/user-guide.md"]
PURPOSE = re.compile(r"This (?:guide|document) describes (.+)\.")


def test_documentation_index_holds_the_purpose_of_each_document():
    lines = README.read_text(encoding="utf-8").splitlines()
    for document in PURPOSE_DOCS:
        text = (ROOT / document).read_text(encoding="utf-8")
        # The purpose is the first paragraph below the title.
        first = text.split("\n\n")[1].strip()
        match = PURPOSE.fullmatch(first)
        assert match, f"{document} must open with 'This guide|document describes ... .'"
        purpose = match[1][0].upper() + match[1][1:]

        rows = [line for line in lines if f"]({document}) |" in line]
        assert len(rows) == 1, f"README.md needs one index row for {document}"
        cells = [cell.strip() for cell in rows[0].strip().strip("|").split("|")]
        assert cells[-1] == purpose, f"README.md index row of {document}"
