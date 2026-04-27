import subprocess
from pathlib import Path

import pytest


def discover_kustomize_dirs():
    top_level = Path("clusters").glob("*/kustomization.yaml")
    crossplane = Path("clusters").glob("*/crossplane/kustomization.yaml")
    hive = Path("clusters").glob("*/hive/kustomization.yaml")
    return sorted([*top_level, *crossplane, *hive])


@pytest.mark.parametrize("kustomization", discover_kustomize_dirs(), ids=str)
def test_kustomize_build(kustomization):
    result = subprocess.run(
        ["kustomize", "build", str(kustomization.parent)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
