import subprocess
from pathlib import Path

import pytest


def discover_kustomize_dirs():
    return sorted(Path("clusters").glob("*/kustomization.yaml"))


@pytest.mark.parametrize("kustomization", discover_kustomize_dirs(), ids=str)
def test_kustomize_build(kustomization):
    result = subprocess.run(
        ["kustomize", "build", str(kustomization.parent)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
