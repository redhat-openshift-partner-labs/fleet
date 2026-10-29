"""Structural validation of the fleet-pipeline ClusterRole."""

from pathlib import Path

import yaml

CLUSTERROLE_PATH = (
    Path(__file__).resolve().parents[2] / "tekton" / "rbac" / "clusterrole.yaml"
)


def _resources_for_group(group):
    with open(CLUSTERROLE_PATH) as f:
        role = yaml.safe_load(f)
    return {
        res
        for rule in role["rules"]
        if group in rule.get("apiGroups", [])
        for res in rule.get("resources", [])
    }


def test_pipeline_manages_scoped_aws_iam_kinds():
    # apply-crossplane-credentials applies these for scoped AWS overlays
    resources = _resources_for_group("iam.aws.upbound.io")
    assert {
        "users",
        "policies",
        "userpolicyattachments",
        "accesskeys",
        "roles",
    } <= resources


def test_pipeline_manages_hub_cluster_cronjobs():
    resources = _resources_for_group("batch")
    assert "cronjobs" in resources
