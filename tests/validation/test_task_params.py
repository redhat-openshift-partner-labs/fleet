"""Every parameter a Tekton Task declares is read somewhere in that Task."""

import json
import re
from pathlib import Path

import pytest
import yaml

TASKS_DIR = Path(__file__).resolve().parents[2] / "tekton" / "tasks"
TASK_FILES = sorted(
    path for path in TASKS_DIR.glob("*.yaml") if path.name != "kustomization.yaml"
)


@pytest.mark.parametrize("path", TASK_FILES, ids=lambda path: path.stem)
def test_task_reads_every_param_it_declares(path):
    """A declared param that no field reads is a value every caller still has to pass."""
    spec = yaml.safe_load(path.read_text())["spec"]
    # JSON keeps each string on one line, so a reference is never split by line wrapping
    body = json.dumps({key: value for key, value in spec.items() if key != "params"})
    unused = [
        param["name"]
        for param in spec.get("params", [])
        # `)` ends a plain reference, `[` starts an array index such as `[*]`
        if not re.search(rf"\$\(params\.{re.escape(param['name'])}[)\[]", body)
    ]
    assert not unused, unused
