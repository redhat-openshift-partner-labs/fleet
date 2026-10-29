"""Structural validation for the create-access-paste Tekton task."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path):
    with open(path) as stream:
        return yaml.safe_load(stream)


def test_task_exposes_required_parameters_and_workspace():
    task = _load_yaml(REPO_ROOT / "tekton" / "tasks" / "create-access-paste.yaml")
    params = {param["name"] for param in task["spec"]["params"]}
    workspaces = {workspace["name"] for workspace in task["spec"]["workspaces"]}

    assert task["metadata"]["name"] == "create-access-paste"
    assert {
        "cluster-name",
        "base-domain",
        "privatebin-url",
        "expire",
        "namespace",
        "pipeline-image",
    } <= params
    assert "shared" in workspaces


def test_task_invokes_fleet_cli_with_workspace_kubeconfig():
    task = _load_yaml(REPO_ROOT / "tekton" / "tasks" / "create-access-paste.yaml")
    script = task["spec"]["steps"][0]["script"]

    assert "fleet-create-access-paste" in script
    assert '--kubeconfig-file "$(workspaces.shared.path)/kubeconfig"' in script


def test_config_loader_exposes_privatebin_settings():
    task = _load_yaml(REPO_ROOT / "tekton" / "tasks" / "config-loader.yaml")
    params = {param["name"] for param in task["spec"]["params"]}
    results = {result["name"] for result in task["spec"]["results"]}
    script = task["spec"]["steps"][0]["script"]

    assert {"privatebin-url", "privatebin-expire"} <= params
    assert {"privatebin-url", "privatebin-expire"} <= results
    assert 'resolve "privatebin-url"' in script
    assert 'resolve "privatebin-expire"' in script


def test_configmap_contains_privatebin_defaults():
    configmap = _load_yaml(REPO_ROOT / "tekton" / "configmap-defaults.yaml")
    data = configmap["data"]

    assert data["privatebin-url"] == "https://pastes.openshiftpartnerlabs.com"
    assert data["privatebin-expire"] == "1week"
