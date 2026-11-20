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
