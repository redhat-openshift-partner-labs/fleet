"""Validate the accelerator-specific AI workload overlays."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

AI_WORKLOADS = Path(__file__).resolve().parents[2] / "workloads" / "ai"


def _resources(path):
    kustomization = yaml.safe_load((path / "kustomization.yaml").read_text())
    return kustomization["resources"]


def test_common_overlay_contains_shared_prerequisites():
    assert _resources(AI_WORKLOADS / "common") == [
        "serverless-subscription.yaml",
        "authorino-subscription.yaml",
    ]


def test_gpu_overlay_contains_gpu_resources():
    assert _resources(AI_WORKLOADS / "gpu") == [
        "nfd-subscription.yaml",
        "nfd-operand.yaml",
        "nvidia-gpu-subscription.yaml",
        "nvidia-gpu-cluster-policy.yaml",
    ]


def test_cpu_overlay_references_common_only():
    assert _resources(AI_WORKLOADS / "cpu") == ["../common"]


def test_root_overlay_combines_common_and_gpu():
    assert _resources(AI_WORKLOADS) == ["common", "gpu"]


@pytest.mark.skipif(not shutil.which("kustomize"), reason="needs kustomize")
@pytest.mark.parametrize(
    "overlay",
    ["", "common", "gpu", "cpu"],
)
def test_overlays_build(overlay):
    path = AI_WORKLOADS / overlay
    result = subprocess.run(
        ["kustomize", "build", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
