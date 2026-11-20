"""Structural validation of the fleet-pipeline ClusterRole."""

from pathlib import Path

import pytest
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


# Hub resources that a task deletes with "oc delete": (API group, resource, a task that does).
DELETED_ON_THE_HUB = [
    ("", "namespaces", "cleanup-hub-artifacts"),
    ("", "secrets", "delete-test-vcluster"),
    ("batch", "cronjobs", "cleanup-hub-artifacts"),
    ("route.openshift.io", "routes", "delete-test-vcluster"),
    ("cluster.open-cluster-management.io", "managedclusters", "delete-test-vcluster"),
]


def _allows(group, resource, verb):
    with open(CLUSTERROLE_PATH) as f:
        role = yaml.safe_load(f)
    return any(
        group in rule.get("apiGroups", [])
        and {resource, "*"} & set(rule.get("resources", []))
        and {verb, "*"} & set(rule["verbs"])
        for rule in role["rules"]
    )


@pytest.mark.parametrize(("group", "resource", "task"), DELETED_ON_THE_HUB)
def test_pipeline_may_delete_what_its_tasks_delete(group, resource, task):
    assert _allows(group, resource, "delete"), f"{task} deletes {resource}"
