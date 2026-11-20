"""Checks that target-architecture.svg matches its layout script and its source."""

import re
import subprocess
import sys
from pathlib import Path

DIAGRAMS = Path(__file__).parents[2] / "docs" / "diagrams"
SCRIPT = DIAGRAMS / "layout_target_architecture.py"
SVG = DIAGRAMS / "target-architecture.svg"
SOURCE = DIAGRAMS / "target-architecture.mermaid"


def test_svg_matches_layout_script():
    # --check exits 1 when the committed SVG differs from the script output.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_svg_holds_every_node_and_edge_of_the_source():
    source = SOURCE.read_text(encoding="utf-8").splitlines()
    # The legend repeats one edge of each style; count the diagram only.
    diagram = SVG.read_text(encoding="utf-8").split("<!-- ===== Legend")[0]

    nodes = sum(bool(re.match(r'\s+\w+\["', line)) for line in source)
    solid = sum("-->|" in line for line in source)
    dashed = sum("-.->|" in line for line in source)

    assert diagram.count('class="badge-t"') == nodes
    assert diagram.count('<path class="flow"') == solid
    assert diagram.count('<path class="ctl"') == dashed
