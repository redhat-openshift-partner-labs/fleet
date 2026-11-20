"""Lay out the pipeline sequence diagrams docs/diagrams/<pipeline>-sequence.svg.

Usage:
    python docs/diagrams/layout_pipeline_sequences.py           # write the SVGs
    python docs/diagrams/layout_pipeline_sequences.py --check   # exit 1 if one differs

Each <pipeline>-sequence.mermaid is the content source: its participants, one
rect per task with the task name in a note, the messages and the %% notes.
SEQUENCES holds what the source does not: the title, the subtitle and the x
of every lifeline.
"""

import argparse
import re
import sys
import textwrap
from pathlib import Path

from drawing import DIAGRAMS, Drawing, emit, shared_head

CHAR_S = 6.0  # estimated width of one 11 px character
HEAD_H = 40  # height of a participant card

ROLES = {  # card role per participant; the pipeline itself is "src"
    "Hub API": "core",
    "Hive": "core",
    "Crossplane": "src",
    "AWS": "gate",
    "GitHub": "gate",
    "Keycloak": "gate",
    "PrivateBin": "gate",
    "Git": "store",
    "Spoke API": "out",
}
LEGEND = {  # legend text per card role, in legend order
    "gate": "external endpoint",
    "src": "pipeline and hub operators",
    "core": "hub cluster control",
    "store": "git",
    "out": "spoke",
}

# xs: x of each lifeline, in the order of the participants in the source.
SEQUENCES = {
    "pre-provision": {
        "title": "pre-provision pipeline: sequence",
        "subtitle": "The calls each of the fourteen tasks makes, in an order the "
        "pipeline allows.",
        "xs": (380, 640, 810, 980, 1150),
    },
    "provision": {
        "title": "provision pipeline: sequence",
        "subtitle": "The calls each of the eleven tasks makes, in an order the "
        "pipeline allows.",
        "xs": (380, 620, 770, 910, 1050, 1170),
    },
    "post-provision": {
        "title": "post-provision pipeline: sequence",
        "subtitle": "The calls each of the twenty-three tasks makes, in an order the "
        "pipeline allows.",
        "xs": (380, 600, 740, 860, 960, 1060, 1170),
    },
    "deprovision": {
        "title": "deprovision pipeline: sequence",
        "subtitle": "The calls each of the seven tasks makes, in the order the tasks run.",
        "xs": (380, 620, 770, 910, 1050, 1170),
    },
}

NOTE = re.compile(r"%% ([^:]+): (.+)")
PARTICIPANT = re.compile(r"\s*participant (\w+)(?: as (.+))?")
OPT = re.compile(r"\s*opt (.+)")
TASK = re.compile(r"\s*Note over \w+,\w+: (.+)")
MESSAGE = re.compile(r"\s*(\w+)(-->>|->>)(\w+): (.+)")


def parse(path: Path) -> dict:
    """Read notes, participants and the messages of every task from a sequence source.

    A task is (name, condition, messages). The condition joins the texts of
    the opt blocks that enclose the task's rect.
    """
    src: dict = {"notes": [], "names": {}, "tasks": []}
    blocks: list[str] = []  # open blocks: an opt's text, or "" for a rect
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := NOTE.fullmatch(line):
            src["notes"].append(match.groups())
        elif match := PARTICIPANT.fullmatch(line):
            src["names"][match[1]] = match[2] or match[1]
        elif match := OPT.fullmatch(line):
            blocks.append(match[1])
        elif line.strip().startswith("rect "):
            blocks.append("")
        elif line.strip() == "end":
            blocks.pop()
        elif match := TASK.fullmatch(line):
            condition = " and ".join(text for text in blocks if text)
            src["tasks"].append((match[1], condition, []))
        elif match := MESSAGE.fullmatch(line):
            sender, arrow, receiver, label = match.groups()
            cls = "flow" if arrow == "->>" else "ctl"
            text = label.replace("<br/>", " ")
            src["tasks"][-1][2].append((sender, receiver, cls, text))
    return src


def wrap(name: str, label: str, room: int) -> list[str]:
    """Wrap a message label to the space before the next lifeline; at most 3 lines."""
    # Resource names keep their hyphens on one line.
    lines = textwrap.wrap(label, max(int(room / CHAR_S), 1), break_on_hyphens=False)
    if len(lines) > 3 or any(len(line) * CHAR_S > room for line in lines):
        sys.exit(f"{name}-sequence.mermaid: shorten the label '{label}'")
    return lines


def describe(name: str, src: dict) -> str:
    """Plain-sentence content of the diagram for the <desc> element."""
    names = src["names"]
    parts = [
        f"Sequence of the {name} pipeline between {', '.join(names.values())}.",
    ]
    for task, condition, messages in src["tasks"]:
        calls = [f"{names[a]} to {names[b]}: {text}" for a, b, _, text in messages]
        when = f" (runs when {condition})" if condition else ""
        parts.append(f"{task}{when}: {'; '.join(calls)}.")
    parts.append("Constraints: " + " ".join(f"{k}: {v}." for k, v in src["notes"]))
    return " ".join(parts)


def render(name: str, spec: dict, head: str) -> str:
    """Return the SVG text of one sequence diagram; head is the <style>...</defs> block."""
    src = parse(DIAGRAMS / f"{name}-sequence.mermaid")
    ids = list(src["names"])
    x_of = dict(zip(ids, spec["xs"]))
    xs = sorted(spec["xs"])
    head_y = 98 + 26 + 32 * (len(src["notes"]) - 1) + 16 + 28

    # Lay out every task group: a frame, and one row per message.
    groups = []
    y = head_y + HEAD_H + 20
    for task, condition, messages in src["tasks"]:
        top = y
        rows = []
        for sender, receiver, cls, text in messages:
            x1, x2 = x_of[sender], x_of[receiver]
            left = min(x1, x2)
            # The label stays left of the next lifeline so that no line crosses it.
            lines = wrap(name, text, xs[xs.index(left) + 1] - left - 16)
            y += (30 if rows else 32) + 14 * (len(lines) - 1)
            end = x2 - 2 if x2 > x1 else x2 + 2
            rows.append((cls, f"M{x1} {y} H{end}", left + 8, y - 7, lines))
        # A condition is a second line below the task name.
        y = max(y + 18, top + (64 if condition else 0))
        groups.append((task, condition, top, y - top, rows))
        y += 10
    bottom = y
    height = bottom + 106

    d = Drawing()
    d.begin(height, spec["title"], describe(name, src), head, spec["subtitle"])
    keys = max(len(key) for key, _ in src["notes"])
    d.constraints(
        [(key, "m b", value) for key, value in src["notes"]],
        max(160, 56 + round(keys * 7.2) + 24),
    )

    d.section("Frames: one per task")
    for _, _, top, tall, _ in groups:
        d.raw(
            f'  <rect class="frame" x="24" y="{top}" width="1214" height="{tall}" rx="14"/>'
        )

    # A participant is a card without badge and body; its lifeline is a rule.
    d.section("Participants and lifelines")
    roles = []
    for i, ident in enumerate(ids):
        title = src["names"][ident]
        role = ROLES.get(title, "src")
        roles.append(role)
        x = x_of[ident]
        width = round(len(title) * 8.2) + 28
        d.raw(
            f'  <rect class="{role}" x="{x - width // 2}" y="{head_y}" '
            f'width="{width}" height="{HEAD_H}" rx="12"/>'
        )
        d.text("t h2", x, head_y + 25, title, anchor="middle")
        d.raw(
            f'  <line class="rule" x1="{x}" y1="{head_y + HEAD_H}" '
            f'x2="{x}" y2="{bottom}"/>'
        )
        if i == 0:
            d.text("m lbl", 40, head_y + 25, "TASK")

    # Tasks are numbered in the order they appear in the source.
    d.section("Tasks")
    for number, (task, condition, top, _, _) in enumerate(groups, 1):
        d.raw(
            f'  <circle class="badge-src" cx="58" cy="{top + 22}" r="10"/>'
            f'<text class="badge-t" x="58" y="{top + 26}" text-anchor="middle">'
            f"{number}</text>"
        )
        d.text("c b", 76, top + 26, task)
        if condition:
            d.text("m s", 76, top + 46, f"when {condition}")

    # Every arrow ends 2 px before its lifeline so the tip touches the line.
    d.section("Messages")
    for _, _, _, _, rows in groups:
        for cls, path, lx, ly, lines in rows:
            d.edge(cls, path)
            for i, line in enumerate(lines):
                d.text("m s", lx, ly - 14 * (len(lines) - 1 - i), line)

    x = 40
    edges = []
    for cls, text in (("flow", "call"), ("ctl", "result or event")):
        edges.append((x, cls, text))
        x += 46 + round(len(text) * CHAR_S) + 34
    swatches = []
    for role, text in LEGEND.items():
        if role in roles:
            swatches.append((x, role, text))
            x += 30 + round(len(text) * CHAR_S) + 34
    d.legend(height, edges, swatches)
    return d.end()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if an SVG differs; write nothing"
    )
    args = parser.parse_args()
    head = shared_head()
    for name, spec in SEQUENCES.items():
        svg = DIAGRAMS / f"{name}-sequence.svg"
        emit(svg, render(name, spec, head), args.check, Path(__file__).name)


if __name__ == "__main__":
    main()
