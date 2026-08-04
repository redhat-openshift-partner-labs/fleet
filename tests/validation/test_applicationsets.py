"""Validate the ArgoCD ApplicationSet and ACM Placement manifests.

These tests parse bootstrap/argocd-applicationsets.yaml and verify that the
hub-to-spoke workload delivery configuration is structurally correct. They
run offline (no cluster needed) by reading YAML directly from disk.
"""

from pathlib import Path

import pytest
import yaml

APPSETS_FILE = Path("bootstrap/argocd-applicationsets.yaml")


def test_applicationsets_file_valid_yaml():
    """Ensure the ApplicationSets file exists and contains valid YAML."""
    assert APPSETS_FILE.exists(), f"{APPSETS_FILE} not found"
    docs = list(yaml.safe_load_all(APPSETS_FILE.read_text()))
    assert len(docs) >= 1, "File should contain at least one YAML document"


def test_applicationsets_expected_resources():
    """Verify the file contains both ApplicationSet and Placement resources.

    Each ApplicationSet needs a paired Placement to select target clusters
    via ACM's cluster decision resource generator.
    """
    docs = list(yaml.safe_load_all(APPSETS_FILE.read_text()))
    kinds = {d["kind"] for d in docs if d}
    assert "ApplicationSet" in kinds
    assert "Placement" in kinds


def test_applicationsets_tier_coverage():
    """Confirm ApplicationSets exist for every supported cluster tier.

    The fleet delivers workloads in tiers: 'base' goes to all clusters,
    'ai' goes only to GPU-enabled clusters labeled tier=ai.
    """
    docs = list(yaml.safe_load_all(APPSETS_FILE.read_text()))
    appset_names = {
        d["metadata"]["name"] for d in docs if d and d["kind"] == "ApplicationSet"
    }
    assert "fleet-workloads-base" in appset_names
    assert "fleet-workloads-ai" in appset_names


def test_placements_have_label_selectors():
    """Ensure every Placement requires the 'bootstrapped' label.

    Spoke clusters are labeled bootstrapped=true only after post-provision
    completes. This prevents workload delivery to partially-ready clusters.
    """
    docs = list(yaml.safe_load_all(APPSETS_FILE.read_text()))
    placements = [d for d in docs if d and d["kind"] == "Placement"]

    for p in placements:
        selectors = p["spec"]["predicates"]
        assert (
            len(selectors) >= 1
        ), f"Placement {p['metadata']['name']} needs at least one predicate"

        labels = (
            selectors[0]
            .get("requiredClusterSelector", {})
            .get("labelSelector", {})
            .get("matchLabels", {})
        )
        assert (
            "bootstrapped" in labels
        ), f"Placement {p['metadata']['name']} must select on bootstrapped label"


def test_ai_applicationset_points_to_workloads_ai():
    """Verify the AI ApplicationSet sources manifests from workloads/ai.

    This path contains the app-of-apps parent kustomization that creates
    the phased ArgoCD Applications for the AI tier operators.
    """
    docs = list(yaml.safe_load_all(APPSETS_FILE.read_text()))
    ai_appsets = [
        d
        for d in docs
        if d
        and d["kind"] == "ApplicationSet"
        and d["metadata"]["name"] == "fleet-workloads-ai"
    ]
    assert len(ai_appsets) == 1
    path = ai_appsets[0]["spec"]["template"]["spec"]["source"]["path"]
    assert path == "workloads/ai"
