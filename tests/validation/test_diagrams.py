"""Checks that the SVGs in docs/diagrams match their layout scripts and sources."""

import re
import subprocess
import sys
from pathlib import Path

DIAGRAMS = Path(__file__).parents[2] / "docs" / "diagrams"


def check(script: str) -> subprocess.CompletedProcess:
    # --check exits 1 when a committed SVG differs from the script output.
    return subprocess.run(
        [sys.executable, str(DIAGRAMS / script), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_architecture_svg_matches_layout_script():
    result = check("layout_architecture.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_architecture_svg_holds_every_node_and_edge_of_the_source():
    source = (DIAGRAMS / "architecture.mermaid").read_text(encoding="utf-8")
    lines = source.splitlines()
    svg = (DIAGRAMS / "architecture.svg").read_text(encoding="utf-8")
    # The legend repeats one edge of each style; count the diagram only.
    diagram = svg.split("<!-- ===== Legend")[0]

    nodes = sum(bool(re.match(r'\s+\w+\["', line)) for line in lines)
    solid = sum("-->|" in line for line in lines)
    dashed = sum("-.->|" in line for line in lines)
    notes = sum(line.startswith("%% ") for line in lines)

    assert diagram.count('class="badge-t"') == nodes
    assert diagram.count('<path class="flow"') == solid
    assert diagram.count('<path class="ctl"') == dashed
    # Every %% note of the source is one row of the constraints band.
    assert diagram.count('class="t b k"') == notes
