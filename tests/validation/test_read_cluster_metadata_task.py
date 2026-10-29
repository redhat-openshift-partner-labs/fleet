"""Run the read-cluster-metadata Task script and check result values byte-for-byte.

Tekton stores result files verbatim and `when` expressions compare exactly, so a trailing
newline (e.g. from `jq -r`) makes `in ["scoped"]` evaluate false and silently skips tasks.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

TASK_PATH = (
    Path(__file__).resolve().parents[2]
    / "tekton"
    / "tasks"
    / "read-cluster-metadata.yaml"
)

pytestmark = pytest.mark.skipif(
    not (shutil.which("bash") and shutil.which("jq")), reason="needs bash and jq"
)


def _run_task_script(tmp_path, metadata):
    task = yaml.safe_load(TASK_PATH.read_text())
    results = [r["name"] for r in task["spec"]["results"]]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "fleet-read-cluster-metadata"
    fake.write_text(f"#!/usr/bin/env bash\necho '{json.dumps(metadata)}'\n")
    fake.chmod(0o755)

    # Emulate Tekton variable substitution
    script = task["spec"]["steps"][0]["script"]
    script = script.replace("$(workspaces.source.path)", str(tmp_path))
    script = script.replace("$(params.cluster-name)", "c1")
    script = re.sub(
        r"\$\(results\.([a-z-]+)\.path\)", lambda m: str(tmp_path / m.group(1)), script
    )
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    subprocess.run(["bash", "-c", script], check=True, env=env, capture_output=True)
    return {name: (tmp_path / name).read_bytes() for name in results}


def test_results_have_no_trailing_newline(tmp_path):
    values = _run_task_script(
        tmp_path,
        {
            "htpasswd-provider-name": "Acme Corp",
            "openshift-ai-version": "v2",
            "ai-accelerator": "none",
            "platform": "aws",
            "aws-credentials-mode": "scoped",
            "timezone": "America/Chicago",
            "schedule": "00 08 * * 1-5",
        },
    )
    assert values == {
        "htpasswd-provider-name": b"Acme Corp",
        "openshift-ai-version": b"v2",
        "ai-accelerator": b"none",
        "platform": b"aws",
        "aws-credentials-mode": b"scoped",
        "timezone": b"America/Chicago",
        "schedule": b"00 08 * * 1-5",
    }


def test_defaults_when_keys_absent(tmp_path):
    values = _run_task_script(tmp_path, {})
    assert values == {
        "htpasswd-provider-name": b"htpasswd",
        "openshift-ai-version": b"v3",
        "ai-accelerator": b"nvidia-gpu",
        "platform": b"aws",
        "aws-credentials-mode": b"legacy",
        "timezone": b"America/Chicago",
        "schedule": b"00 08 * * 1-5",
    }
