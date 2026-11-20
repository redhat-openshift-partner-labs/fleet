"""Lay out the pipeline task flowcharts docs/diagrams/<pipeline>-flow.svg.

Usage:
    python docs/diagrams/layout_pipeline_flows.py           # write the SVGs
    python docs/diagrams/layout_pipeline_flows.py --check   # exit 1 if one differs

Each <pipeline>-flow.mermaid is the content source: its nodes, edges, labels,
subgraphs, classes and %% notes. FLOWS holds what the source does not: the
title, the subtitle and the grid position of every task.
"""

import argparse
import re
import sys
from pathlib import Path

from drawing import DIAGRAMS, Drawing, emit, pill_width, shared_head

# Three card columns with a 96 px channel between them.
COL_X = (40, 466, 892)
COL_W, COL_GAP = 330, 96
ROW_GAP, FRAME_GAP = 56, 52  # between rows in one frame, between two frames
CHAR_S = 6.0  # estimated width of one 11 px character

ROLES = {  # legend text per card role, in legend order
    "gate": "external endpoint",
    "src": "workspace, git, configuration",
    "core": "hub Kubernetes API",
    "out": "spoke",
}

LANE_12 = 844  # x of the lane between columns 1 and 2
COL_2 = 1057  # x of the centre of column 2

# place: node id -> (column, row, columns spanned).
# via: (source, target) -> x of the lane an edge takes past other rows.
# frame_cols: subgraph id -> (first column, columns spanned); default is the full width.
# frame_rows: subgraph id -> (first row, last row); default is the rows of its members.
FLOWS = {
    "pre-provision": {
        "title": "pre-provision pipeline",
        "subtitle": "Fourteen tasks check the cluster definition, create the hub namespace, "
        "secrets and AWS credentials, then start the provision pipeline.",
        "place": {
            "load_config": (0, 0, 1),
            "git_clone": (1, 0, 1),
            "check_prefix_collision": (2, 0, 1),
            "read_cluster_metadata": (0, 1, 1),
            "create_cluster_namespace": (2, 1, 1),
            "create_ssh_key": (1, 2, 1),
            "create_pull_secret": (2, 2, 1),
            "apply_crossplane_credentials": (0, 3, 1),
            "wait_for_aws_credentials": (1, 3, 1),
            "transform_aws_credentials": (2, 3, 1),
            "wait_for_aws_component_credentials": (0, 4, 1),
            "build_aws_credentials_manifests": (1, 4, 1),
            "validate_cluster_inputs": (1, 5, 1),
            "trigger_provision": (2, 5, 1),
        },
        # The legacy path passes the scoped frame in column 2.
        "via": {("transform_aws_credentials", "validate_cluster_inputs"): COL_2},
        "frame_cols": {"Scoped": (0, 2)},
    },
    "provision": {
        "title": "provision pipeline",
        "subtitle": "Eleven tasks apply the cluster resources, wait for the install and "
        "the ACM join, then start the post-provision pipeline.",
        "place": {
            "load_config": (0, 0, 1),
            "git_clone": (1, 0, 1),
            "read_cluster_metadata": (2, 0, 1),
            "apply_cluster_crs": (0, 1, 1),
            "wait_for_hive_ready": (1, 1, 1),
            "wait_for_managed_cluster": (1, 2, 1),
            "scope_aws_credentials": (2, 2, 1),
            "extract_spoke_kubeconfig": (0, 3, 1),
            "read_cluster_tier": (1, 3, 1),
            "label_for_post_provision": (0, 4, 1),
            "trigger_post_provision": (0, 5, 3),
        },
        # The metadata edge passes scope-aws-credentials between columns 1 and 2.
        # It crosses the edge from wait-for-hive-ready to scope-aws-credentials.
        "via": {("read_cluster_metadata", "trigger_post_provision"): LANE_12},
        "frame_cols": {"Membership": (0, 2), "Scoped": (2, 1)},
    },
    "deprovision": {
        "title": "deprovision pipeline",
        "subtitle": "Seven tasks delete a cluster, its cloud resources and its hub "
        "artifacts, then report the result to fleet-clusters.",
        "place": {
            "load_config": (0, 0, 3),
            "terminate_pod_vms": (0, 1, 1),
            "delete_cluster_resources": (1, 1, 1),
            "wait_hive_uninstall": (2, 1, 1),
            "cleanup_hub_artifacts": (0, 2, 1),
            "verify_deprovision": (1, 2, 1),
            "create_deployment_status": (2, 2, 1),
        },
    },
}

NOTE = re.compile(r"%% ([^:]+): (.+)")
SUBGRAPH = re.compile(r'\s*subgraph (\w+)\["(.+)"\]')
NODE = re.compile(r'\s*(\w+)\["(.+)"\]')
EDGE = re.compile(r"\s*(\w+) -->(?:\|(.+)\|)? (\w+)")
CLASS = re.compile(r"\s*class ([\w,]+) (\w+)")


def parse(path: Path) -> dict:
    """Read notes, subgraphs, nodes, edges and roles from a flowchart source."""
    src: dict = {"notes": [], "groups": [], "nodes": {}, "edges": [], "roles": {}}
    stack: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := NOTE.fullmatch(line):
            src["notes"].append(match.groups())
        elif match := SUBGRAPH.fullmatch(line):
            group = {"id": match[1], "title": match[2], "depth": len(stack)}
            group["members"] = []
            src["groups"].append(group)
            stack.append(group)
        elif line.strip() == "end":
            stack.pop()
        elif match := NODE.fullmatch(line):
            title, *body = match[2].split("<br/>")
            src["nodes"][match[1]] = (title, body)
            for group in stack:
                group["members"].append(match[1])
        elif match := EDGE.fullmatch(line):
            src["edges"].append((match[1], match[3], match[2] or ""))
        elif match := CLASS.fullmatch(line):
            for node in match[1].split(","):
                src["roles"][node] = match[2]
    return src


def span_width(span: int) -> int:
    return COL_W * span + COL_GAP * (span - 1)


def rows_of(src: dict, spec: dict, top: int) -> tuple[dict, dict, dict]:
    """Return card boxes, the channel y above each row, and frame boxes.

    A box is (x, y, width, height). Rows are stacked from top downwards; a
    frame adds 26 px above its first row and 16 px below its last row.
    """
    place = spec["place"]
    for group in src["groups"]:
        rows = [place[m][1] for m in group["members"]]
        group["rows"] = spec.get("frame_rows", {}).get(
            group["id"], (min(rows), max(rows))
        )
    groups = sorted(src["groups"], key=lambda g: g["depth"])

    boxes: dict = {}
    channel: dict = {}
    frames: dict = {}
    frame_top: dict = {}
    y = top
    bottom = top
    for row in sorted({r for _, r, _ in place.values()}):
        starting = [g for g in groups if g["rows"][0] == row]
        ending = [g for g in groups if g["rows"][1] == row]
        if row:
            gap = FRAME_GAP if starting else ROW_GAP
            channel[row] = bottom + gap // 2
            y = bottom + gap
        # Frames of one depth that start on the same row share their top edge.
        for depth in sorted({g["depth"] for g in starting}):
            for group in starting:
                if group["depth"] == depth:
                    frame_top[group["id"]] = y
            y += 26
        members = [n for n, (_, r, _) in place.items() if r == row]
        lines = max(len(src["nodes"][n][1]) for n in members)
        height = 80 + 18 * max(lines - 1, 0)
        for node in members:
            col, _, span = place[node]
            boxes[node] = (COL_X[col], y, span_width(span), height)
        bottom = y + height
        # Inner frames close first; frames of one depth share their bottom edge.
        for depth in sorted({g["depth"] for g in ending}, reverse=True):
            bottom += 16
            for group in ending:
                if group["depth"] != depth:
                    continue
                fx, fw = 24, 1214
                if group["id"] in spec.get("frame_cols", {}):
                    col, span = spec["frame_cols"][group["id"]]
                    fx, fw = COL_X[col] - 16, span_width(span) + 32
                ftop = frame_top[group["id"]]
                frames[group["id"]] = (fx, ftop, fw, bottom - ftop)
    return boxes, channel, frames


def route(src_box, dst_box, turn: int, chan: int, via) -> tuple[str, list, tuple]:
    """Return the path, its vertical segments, and the label anchor of an edge.

    Same row: a horizontal line. Rows below: a vertical line where the two
    cards overlap, otherwise an elbow through chan, the channel above the
    target. With via, the edge passes other rows at x = via: it turns into
    that lane in the channel below the source (turn) and leaves it at chan.
    The label anchor is (x, y, text-anchor).
    """
    sx, sy, sw, sh = src_box
    dx, dy, dw, _ = dst_box
    if sy == dy:
        y = sy + sh // 2
        mid = (sx + sw + dx) // 2
        return f"M{sx + sw} {y} H{dx - 2}", [], (mid, y - 7, "middle")

    start, end = sy + sh, dy - 2
    left, right = max(sx, dx), min(sx + sw, dx + dw)
    label_y = chan + 15
    if via is None and left < right:
        # Straight down the centre of the narrower card.
        x = dx + dw // 2 if dw <= sw else sx + sw // 2
        return f"M{x} {start} V{end}", [(x, start, end)], (x + 8, label_y, "")

    xs, xt = sx + sw // 2, dx + dw // 2
    if via is None:
        path = f"M{xs} {start} V{chan} H{xt} V{end}"
        return path, [(xs, start, chan), (xt, chan, end)], (xt + 8, label_y, "")

    # A lane inside a card's width is that card's exit or entry point.
    xs = via if sx <= via <= sx + sw else xs
    xt = via if dx <= via <= dx + dw else xt
    path, lane_top, segments = f"M{xs} {start}", start, []
    if xs != via:
        path += f" V{turn} H{via}"
        segments.append((xs, start, turn))
        lane_top = turn
    if xt != via:
        path += f" V{chan} H{xt} V{end}"
        segments += [(via, lane_top, chan), (xt, chan, end)]
    else:
        path += f" V{end}"
        segments.append((via, lane_top, end))
    return path, segments, (xt + 8, label_y, "")


def pill_x(frame, name: str, blocked: list) -> int:
    """Leftmost pill position on the frame's top edge that no edge or label crosses."""
    fx, fy, _, _ = frame
    width = pill_width(name)
    px = fx + 16
    for lo, hi, y1, y2 in sorted(blocked):
        if y1 <= fy + 10 and y2 >= fy - 10 and px < hi + 8 and px + width > lo - 8:
            px = hi + 10
    if px + width > fx + frame[2] - 16:
        sys.exit(f"frame '{name}': no room for its pill; shorten the subgraph title")
    return px


def describe(name: str, src: dict) -> str:
    """Plain-sentence content of the diagram for the <desc> element."""
    parts = [f"The {name} pipeline has {len(src['nodes'])} tasks."]
    for group in src["groups"]:
        tasks = [
            f"{src['nodes'][m][0]} ({' '.join(src['nodes'][m][1])})"
            for m in group["members"]
        ]
        parts.append(f"{group['title']}: {'; '.join(tasks)}.")
    for before, after, label in src["edges"]:
        when = f" when {label}" if label else ""
        title = src["nodes"]
        parts.append(f"{title[after][0]} runs after {title[before][0]}{when}.")
    parts.append("Constraints: " + " ".join(f"{k}: {v}." for k, v in src["notes"]))
    return " ".join(parts)


def render(name: str, spec: dict, head: str) -> str:
    """Return the SVG text of one flowchart; head is the <style>...</defs> block."""
    src = parse(DIAGRAMS / f"{name}-flow.mermaid")
    place = spec["place"]
    band_bottom = 98 + 26 + 32 * (len(src["notes"]) - 1) + 16
    boxes, channel, frames = rows_of(src, spec, band_bottom + 34)

    # Edges first: frame pills are placed where no edge or label crosses.
    paths, labels, blocked = [], [], []
    for before, after, label in src["edges"]:
        via = spec.get("via", {}).get((before, after))
        chan = channel.get(place[after][1], 0)
        turn = channel.get(place[before][1] + 1, 0)
        path, segments, anchor = route(boxes[before], boxes[after], turn, chan, via)
        paths.append(path)
        blocked += [(x, x, y1, y2) for x, y1, y2 in segments]
        if label:
            lx, ly, side = anchor
            labels.append((lx, ly, label, side))
            blocked.append((lx, lx + round(len(label) * CHAR_S), ly - 10, ly + 4))

    height = max(y + h for _, y, _, h in frames.values()) + 106
    d = Drawing()
    d.begin(height, spec["title"], describe(name, src), head, spec["subtitle"])
    keys = max(len(key) for key, _ in src["notes"])
    d.constraints(
        [(key, "m b", value) for key, value in src["notes"]],
        max(160, 56 + round(keys * 7.2) + 24),
    )

    d.section("Frames")
    for group in sorted(src["groups"], key=lambda g: g["depth"]):
        frame = frames[group["id"]]
        title = group["title"].upper()
        d.frame(group["depth"] > 0, *frame, pill_x(frame, title, blocked), title)

    # Cards are numbered in reading order: by row, then by column.
    d.section("Cards")
    for node in sorted(place, key=lambda n: (place[n][1], place[n][0])):
        title, body = src["nodes"][node]
        d.card(
            src["roles"][node], *boxes[node], title, [("m s", line) for line in body]
        )

    # Every path ends 2 px before its target so the arrow tip touches the border.
    d.section("Edges")
    for path in paths:
        d.edge("flow", path)
    for lx, ly, label, side in labels:
        d.label(lx, ly, label, anchor=side)

    x = 40 + 46 + round(len("runs next") * CHAR_S) + 34
    roles = []
    for role, text in ROLES.items():
        if role in src["roles"].values():
            roles.append((x, role, text))
            x += 30 + round(len(text) * CHAR_S) + 34
    d.legend(height, [(40, "flow", "runs next")], roles)
    return d.end()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if an SVG differs; write nothing"
    )
    args = parser.parse_args()
    head = shared_head()
    for name, spec in FLOWS.items():
        svg = DIAGRAMS / f"{name}-flow.svg"
        emit(svg, render(name, spec, head), args.check, Path(__file__).name)


if __name__ == "__main__":
    main()
