"""Checks that the two documents on pipeline values match tekton/ and fleet/tasks/."""

import re

import yaml

from tests.validation._markdown import ROOT

METADATA_DOC = ROOT / "docs" / "per-cluster-metadata.md"
METADATA_TASK = ROOT / "tekton" / "tasks" / "read-cluster-metadata.yaml"


def table_rows(path, heading: str) -> dict[str, list[str]]:
    """Rows of the tables in one section of a document, keyed by their first cell.

    The key is the first cell without backticks. A section runs from its
    heading to the next heading of the same level.
    """
    text = path.read_text(encoding="utf-8")
    level = heading.split(" ", 1)[0]
    section = text.split(f"\n{heading}\n", 1)[1].split(f"\n{level} ", 1)[0]
    rows = {}
    for line in section.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[cells[0].strip("`")] = cells
    return rows


def pipeline_task_names() -> set[str]:
    names = set()
    for path in (ROOT / "tekton" / "pipelines").glob("*.yaml"):
        definition = yaml.safe_load(path.read_text(encoding="utf-8"))
        if definition.get("kind") == "Pipeline":
            names |= {task["name"] for task in definition["spec"]["tasks"]}
    return names


def test_key_table_holds_the_results_and_defaults_of_the_metadata_task():
    task = yaml.safe_load(METADATA_TASK.read_text(encoding="utf-8"))["spec"]
    results = {result["name"] for result in task["results"]}
    # The script writes each result as: result "<path>" '.["key"] // "default"'
    script = task["steps"][0]["script"]
    defaults = dict(re.findall(r"'\.\[\"([\w-]+)\"\] // \"([^\"]*)\"'", script))
    assert set(defaults) == results

    rows = table_rows(METADATA_DOC, "## Supported keys")
    keys = {key for key in rows if key != "Key"}
    assert keys == results

    for key in keys:
        expected = f"`{defaults[key]}`" if defaults[key] else "Empty"
        assert rows[key][1] == expected, f"default of {key}"


def test_key_table_names_only_tasks_of_the_pipelines_as_readers():
    rows = table_rows(METADATA_DOC, "## Supported keys")
    tasks = pipeline_task_names()
    for key, cells in rows.items():
        if key == "Key":
            continue
        # Column 4 names the tasks that read the key.
        named = set(re.findall(r"`([\w-]+)`", cells[3]))
        assert named <= tasks, f"{key}: no pipeline has {sorted(named - tasks)}"


THREADING_DOC = ROOT / "docs" / "parameter-threading.md"


def test_trace_quotes_are_in_the_files_they_name():
    rows = table_rows(THREADING_DOC, "## Trace of cluster-name")
    hops = {key: cells for key, cells in rows.items() if key != "Hop"}
    assert hops

    for hop, cells in hops.items():
        # Column 2 names the file, column 3 quotes the expression from it.
        file = cells[1].strip("`")
        quote = cells[2].strip("`")
        text = (ROOT / file).read_text(encoding="utf-8")
        assert quote in text, f"hop {hop}: {file} no longer holds {quote}"


def test_procedure_names_only_files_that_exist():
    text = THREADING_DOC.read_text(encoding="utf-8")
    section = text.split("\n## Add a per-cluster value\n", 1)[1].split("\n## ", 1)[0]
    # A path is a backticked name with a directory and no placeholder.
    paths = [p for p in re.findall(r"`([\w./-]+/[\w./-]+)`", section) if "<" not in p]
    assert paths
    missing = [path for path in paths if not (ROOT / path).exists()]
    assert not missing, f"docs/parameter-threading.md names missing files: {missing}"
