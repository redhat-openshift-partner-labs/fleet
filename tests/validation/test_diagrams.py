"""Checks that the SVGs in docs/diagrams match their layout scripts and sources."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
DIAGRAMS = ROOT / "docs" / "diagrams"
PIPELINES = ROOT / "tekton" / "pipelines"

# Pipelines that have a task flowchart: <pipeline>-flow.mermaid and .svg
FLOWS = ["pre-provision", "provision", "post-provision", "deprovision"]
# Pipelines that have a sequence diagram: <pipeline>-sequence.mermaid and .svg
SEQUENCES = ["pre-provision", "deprovision"]

SHARED_HEAD = re.compile(r"  <style>[\s\S]*?</defs>")
SUBGRAPH = re.compile(r'\s*subgraph \w+\["(.+)"\]')
NODE = re.compile(r'\s*(\w+)\["(.+)"\]')
EDGE = re.compile(r"\s*(\w+) -->(?:\|(.+)\|)? (\w+)")


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


def parse_flow(name: str) -> dict:
    """Return the notes, nodes, edges and subgraph titles of <name>-flow.mermaid."""
    flow: dict = {"notes": 0, "nodes": {}, "edges": [], "groups": 0, "titles": {}}
    open_titles: list[str] = []
    path = DIAGRAMS / f"{name}-flow.mermaid"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%% "):
            flow["notes"] += 1
        elif match := SUBGRAPH.fullmatch(line):
            flow["groups"] += 1
            open_titles.append(match[1])
        elif line.strip() == "end":
            open_titles.pop()
        elif match := NODE.fullmatch(line):
            # The first label line is the task name.
            flow["nodes"][match[1]] = match[2].split("<br/>")[0]
            flow["titles"][match[1]] = " ".join(open_titles)
        elif match := EDGE.fullmatch(line):
            flow["edges"].append((match[1], match[3], match[2] or ""))
    return flow


def pipeline_tasks(name: str) -> list[dict]:
    text = (PIPELINES / f"{name}.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)["spec"]["tasks"]


def node_id(task_name: str) -> str:
    return task_name.replace("-", "_")


def when_tokens(task: dict) -> list[str]:
    """Words a diagram must state for the when conditions of a pipeline task."""
    tokens = []
    for when in task.get("when", []):
        param = re.search(r"([\w-]+)\)$", when["input"])[1]
        # A true/false parameter is stated by its name, any other by its values.
        tokens += [param if value == "true" else value for value in when["values"]]
    return tokens


@pytest.mark.parametrize("name", FLOWS)
def test_flow_source_holds_the_tasks_and_order_of_the_pipeline(name):
    flow = parse_flow(name)
    tasks = pipeline_tasks(name)

    # A node id is the task name with underscores; its first line is the name.
    assert flow["nodes"] == {node_id(task["name"]): task["name"] for task in tasks}

    run_after = {
        (node_id(before), node_id(task["name"]))
        for task in tasks
        for before in task.get("runAfter", [])
    }
    assert {(src, dst) for src, dst, _ in flow["edges"]} == run_after
    assert len(flow["edges"]) == len(run_after)


@pytest.mark.parametrize("name", FLOWS)
def test_flow_source_states_every_when_condition(name):
    flow = parse_flow(name)
    for task in pipeline_tasks(name):
        node = node_id(task["name"])
        labels = " ".join(label for _, dst, label in flow["edges"] if dst == node)
        stated = f"{labels} {flow['titles'][node]}"
        for token in when_tokens(task):
            assert re.search(
                rf"(?<![\w-]){re.escape(token)}(?![\w-])", stated
            ), f"{task['name']}: no incoming edge label or frame title states {token}"


@pytest.mark.parametrize("name", FLOWS)
def test_flow_svg_holds_every_node_edge_frame_and_note(name):
    flow = parse_flow(name)
    svg = (DIAGRAMS / f"{name}-flow.svg").read_text(encoding="utf-8")
    diagram = svg.split("<!-- ===== Legend")[0]

    assert diagram.count('class="badge-t"') == len(flow["nodes"])
    assert diagram.count('<path class="flow"') == len(flow["edges"])
    assert diagram.count('class="t b k"') == flow["notes"]
    # One label names the CONSTRAINTS band; the others are the frame pills.
    assert diagram.count('class="m lbl"') == flow["groups"] + 1


def test_flow_svgs_match_layout_script():
    result = check("layout_pipeline_flows.py")
    assert result.returncode == 0, result.stdout + result.stderr


def parse_sequence(name: str) -> dict:
    """Return the counts and the task names of <name>-sequence.mermaid."""
    seq: dict = {"notes": 0, "participants": 0, "tasks": [], "calls": 0, "results": 0}
    seq["conditions"] = {}
    blocks: list[str] = []  # open blocks: an opt's text, or "" for a rect
    path = DIAGRAMS / f"{name}-sequence.mermaid"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%% "):
            seq["notes"] += 1
        elif re.fullmatch(r"\s*participant \w+( as .+)?", line):
            seq["participants"] += 1
        elif match := re.fullmatch(r"\s*opt (.+)", line):
            blocks.append(match[1])
        elif line.strip().startswith("rect "):
            blocks.append("")
        elif line.strip() == "end":
            blocks.pop()
        elif match := re.fullmatch(r"\s*Note over \w+,\w+: (.+)", line):
            # The note of a rect names the task whose messages follow.
            seq["tasks"].append(match[1])
            seq["conditions"][match[1]] = " ".join(blocks)
        elif match := re.fullmatch(r"\s*\w+(-->>|->>)\w+: .+", line):
            seq["calls" if match[1] == "->>" else "results"] += 1
    return seq


@pytest.mark.parametrize("name", SEQUENCES)
def test_sequence_source_holds_the_tasks_of_the_pipeline_in_run_order(name):
    shown = parse_sequence(name)["tasks"]
    tasks = pipeline_tasks(name)

    assert sorted(shown) == sorted(task["name"] for task in tasks)
    for task in tasks:
        for before in task.get("runAfter", []):
            assert shown.index(before) < shown.index(
                task["name"]
            ), f"{task['name']} is shown before {before}"


@pytest.mark.parametrize("name", SEQUENCES)
def test_sequence_source_states_every_when_condition(name):
    conditions = parse_sequence(name)["conditions"]
    for task in pipeline_tasks(name):
        for token in when_tokens(task):
            assert re.search(
                rf"(?<![\w-]){re.escape(token)}(?![\w-])", conditions[task["name"]]
            ), f"{task['name']}: no enclosing opt block states {token}"


@pytest.mark.parametrize("name", SEQUENCES)
def test_sequence_svg_holds_every_participant_task_message_and_note(name):
    seq = parse_sequence(name)
    svg = (DIAGRAMS / f"{name}-sequence.svg").read_text(encoding="utf-8")
    diagram = svg.split("<!-- ===== Legend")[0]

    # A participant title is the only centred h2 text.
    titles = re.findall(r'class="t h2"[^>]*text-anchor="middle"', diagram)
    assert len(titles) == seq["participants"]
    assert diagram.count('class="badge-t"') == len(seq["tasks"])
    assert diagram.count('<path class="flow"') == seq["calls"]
    assert diagram.count('<path class="ctl"') == seq["results"]
    assert diagram.count('class="t b k"') == seq["notes"]


def test_sequence_svgs_match_layout_script():
    result = check("layout_pipeline_sequences.py")
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_svg_carries_the_style_and_defs_of_the_architecture_svg():
    architecture = (DIAGRAMS / "architecture.svg").read_text(encoding="utf-8")
    expected = SHARED_HEAD.search(architecture)[0]
    files = [f"{name}-flow.svg" for name in FLOWS]
    files += [f"{name}-sequence.svg" for name in SEQUENCES]
    for file in files:
        svg = (DIAGRAMS / file).read_text(encoding="utf-8")
        assert SHARED_HEAD.search(svg)[0] == expected, file
