"""SVG drawing helpers shared by the layout scripts in docs/diagrams/.

Every diagram carries the same <style> and <defs> blocks. They are read from
HEAD_SOURCE and written unchanged into each SVG.
"""

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Drawing helpers take one argument per SVG coordinate.
# pylint: disable=too-many-arguments,too-many-positional-arguments

DIAGRAMS = Path(__file__).parent
HEAD_SOURCE = DIAGRAMS / "architecture.svg"
SHARED_HEAD = re.compile(r"  <style>[\s\S]*?</defs>")

W = 1262  # canvas width of every diagram


def shared_head() -> str:
    """Return the <style>...</defs> block of HEAD_SOURCE."""
    head = SHARED_HEAD.search(HEAD_SOURCE.read_text(encoding="utf-8"))
    if head is None:
        sys.exit(
            f"{HEAD_SOURCE.name}: no <style>...</defs> block; restore the file from git"
        )
    return head.group(0)


def emit(svg: Path, text: str, check: bool, script: str) -> None:
    """Write text to svg, or with check exit 1 when the file differs from text."""
    if not check:
        svg.write_text(text, encoding="utf-8")
        return
    if not svg.exists() or svg.read_text(encoding="utf-8") != text:
        sys.exit(f"{svg.name} differs from the layout; run {script}")


class Drawing:
    """Collects SVG lines; cards are numbered in the order they are added."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.cards = 0

    def raw(self, line: str = "") -> None:
        self.lines.append(line)

    def begin(self, height: int, title: str, desc: str, head: str, subtitle: str):
        """Root element, accessible text, shared head, canvas and title block."""
        self.raw(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" '
            f'width="{W}" height="{height}" role="img" aria-labelledby="title desc">'
        )
        self.raw(f'  <title id="title">{escape(title)}</title>')
        self.raw(f'  <desc id="desc">{escape(desc)}</desc>')
        self.raw()
        self.raw(head)
        self.raw()
        self.raw("  <!-- Canvas -->")
        self.raw(
            f'  <rect class="bg" x="0.5" y="0.5" width="{W - 1}" '
            f'height="{height - 1}" rx="16"/>'
        )
        self.raw()
        self.raw("  <!-- Title -->")
        self.text("t h1", 40, 46, title)
        self.text("m b", 40, 68, subtitle)

    def end(self) -> str:
        self.raw("</svg>")
        return "\n".join(self.lines) + "\n"

    def section(self, name: str) -> None:
        self.raw()
        self.raw(f"  <!-- ===== {name} ===== -->")

    def text(self, cls: str, x: int, y: int, content: str, anchor: str = "") -> None:
        attr = f' text-anchor="{anchor}"' if anchor else ""
        self.raw(
            f'  <text class="{cls}" x="{x}" y="{y}"{attr}>{escape(content)}</text>'
        )

    def constraints(self, rows, vx: int) -> int:
        """Full-width CONSTRAINTS band of (key, value class, value) rows.

        Rows have a 32 px pitch; vx is the x of the value column. Returns the
        y of the band's bottom edge.
        """
        height = 26 + 32 * (len(rows) - 1) + 16
        self.section("Constraints")
        self.text("m lbl", 40, 90, "CONSTRAINTS")
        self.raw(
            f'  <rect class="frame" x="40" y="98" width="1182" height="{height}" rx="12"/>'
        )
        for i, (key, cls, value) in enumerate(rows):
            y = 124 + 32 * i
            if i:
                self.raw(
                    f'  <line class="rule" x1="56" y1="{y - 18}" x2="1206" y2="{y - 18}"/>'
                )
            self.text("t b k", 56, y, key)
            self.text(cls, vx, y, value)
        return 98 + height

    def card(self, role: str, x: int, y: int, w: int, h: int, title: str, body) -> None:
        """Card with badge, title, rule and body lines at an 18 px pitch."""
        self.cards += 1
        self.raw(
            f'  <rect class="{role}" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>'
        )
        self.raw(
            f'  <circle class="badge-{role}" cx="{x + 18}" cy="{y + 20}" r="10"/>'
            f'<text class="badge-t" x="{x + 18}" y="{y + 24}" text-anchor="middle">'
            f"{self.cards}</text>"
        )
        self.text("t h2", x + 34, y + 25, title)
        self.raw(
            f'  <line class="rule" x1="{x + 12}" y1="{y + 40}" '
            f'x2="{x + w - 12}" y2="{y + 40}"/>'
        )
        for i, (cls, line) in enumerate(body):
            self.text(cls, x + 12, y + 62 + 18 * i, line)

    def frame(
        self, nested: bool, x: int, y: int, w: int, h: int, px: int, name: str
    ) -> None:
        """Subgraph frame with a tag pill at px on its top edge."""
        cls, pill = ("bg", "frame") if nested else ("frame", "bg")
        pw = round(8.2 * len(name) + 24)
        self.raw(
            f'  <rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="14"/>'
        )
        self.raw(
            f'  <rect class="{pill}" x="{px}" y="{y - 10}" width="{pw}" height="20" rx="10"/>'
        )
        self.text("m lbl", px + 12, y + 4, name)

    def edge(self, cls: str, path: str) -> None:
        """cls is flow (mermaid -->) or ctl (mermaid -.->)."""
        self.raw(f'  <path class="{cls}" d="{path}" marker-end="url(#a-{cls})"/>')

    def label(self, x: int, y: int, *lines: str, anchor: str = "") -> None:
        for i, line in enumerate(lines):
            self.text("m s", x, y + 14 * i, line, anchor)

    def legend(self, height: int, edges, roles) -> None:
        """Legend row: edges are (x, class, text), roles are (x, role, text)."""
        ly = height - 38
        self.section("Legend")
        self.raw(
            f'  <line class="rule" x1="40" y1="{height - 66}" x2="1222" y2="{height - 66}"/>'
        )
        for x, cls, name in edges:
            self.raw(
                f'  <path class="{cls}" d="M{x} {ly} H{x + 36}" '
                f'marker-end="url(#a-{cls})"/>'
            )
            self.text("m s", x + 46, ly + 4, name)
        for x, role, name in roles:
            self.raw(
                f'  <rect class="{role}" x="{x}" y="{ly - 8}" width="22" height="16" rx="4"/>'
            )
            self.text("m s", x + 30, ly + 4, name)
