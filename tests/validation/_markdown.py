"""Helpers of the document tests: the links and heading anchors of a markdown file."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]

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
    """Targets of the links and images of a markdown file, without external URLs."""
    text = path.read_text(encoding="utf-8")
    return [t for t in LINK_TARGET.findall(text) if not t.startswith(EXTERNAL_PREFIXES)]


def table_rows(path: Path, heading: str) -> dict[str, list[str]]:
    """Rows of the tables in one section of a document, keyed by their first cell.

    The key is the first cell without backticks. A section runs from its
    heading to the next heading of the same or a higher level.
    """
    text = path.read_text(encoding="utf-8")
    depth = len(heading.split(" ", 1)[0])
    rest = text.split(f"\n{heading}\n", 1)[1]
    section = re.split(rf"\n#{{1,{depth}}} ", rest, maxsplit=1)[0]
    rows = {}
    for line in section.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows
