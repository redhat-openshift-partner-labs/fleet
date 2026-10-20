import subprocess
from unittest import mock

from fleet.tasks._aws_components import (
    CLUSTER_LABEL,
    COMPONENTS,
    access_key_name,
    all_iam_targets,
    iam_targets,
    labelled_iam_targets,
    manifests_secret_name,
    raw_secret_name,
)


def test_resource_names():
    assert raw_secret_name("c1", "ingress") == "c1-ingress-credentials-raw"
    assert access_key_name("c1", "ingress") == "c1-ingress-access-key"
    assert manifests_secret_name("c1") == "c1-cloud-credentials-manifests"


def test_components_match_scaffold_credentials_requests():
    # Must stay in sync with fleet-cluster-scaffold aws_policies.COMPONENTS
    assert {(c.key, c.namespace, c.secret) for c in COMPONENTS} == {
        ("machine-api", "openshift-machine-api", "aws-cloud-credentials"),
        (
            "cco-iam-ro",
            "openshift-cloud-credential-operator",
            "cloud-credential-operator-iam-ro-creds",
        ),
        ("image-registry", "openshift-image-registry", "installer-cloud-credentials"),
        ("ingress", "openshift-ingress-operator", "cloud-credentials"),
        ("cncc", "openshift-cloud-network-config-controller", "cloud-credentials"),
        ("ebs-csi", "openshift-cluster-csi-drivers", "ebs-cloud-credentials"),
    }


# ---------------------------------------------------------------------------
# Label discovery: every resource the scaffold labelled, plus the known names
# ---------------------------------------------------------------------------


def _get(stdout, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="denied")


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_labelled_targets_query_and_normalize(mock_run):
    mock_run.return_value = _get(
        "user.iam.aws.upbound.io/c1-extra\naccesskey.iam.aws.upbound.io/c1-extra-key\n"
    )
    assert labelled_iam_targets("c1") == [
        "user.iam/c1-extra",
        "accesskey.iam/c1-extra-key",
    ]
    cmd = mock_run.call_args.args[0]
    assert cmd[:2] == ["oc", "get"]
    assert ["-l", f"{CLUSTER_LABEL}=c1"] == cmd[3:5]
    assert set(cmd[2].split(",")) == {
        f"{r}.iam.aws.upbound.io"
        for r in ("users", "policies", "userpolicyattachments", "accesskeys", "roles")
    }


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_labelled_targets_empty_on_oc_failure(mock_run):
    mock_run.return_value = _get("", returncode=1)
    assert labelled_iam_targets("c1") == []


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_all_targets_union_dedup_and_dependency_order(mock_run):
    mock_run.return_value = _get(
        "user.iam.aws.upbound.io/c1-ocp-installer\n"  # already a known name
        "user.iam.aws.upbound.io/c1-extra\n"
        "userpolicyattachment.iam.aws.upbound.io/c1-extra-attachment\n"
    )
    targets = all_iam_targets("c1")
    assert len(targets) == len(iam_targets("c1")) + 2
    assert len(set(targets)) == len(targets)
    rank = ["userpolicyattachment", "accesskey", "policy", "user", "role"]
    kinds = [rank.index(t.split(".", 1)[0]) for t in targets]
    assert kinds == sorted(kinds)
