import json
import subprocess
from unittest import mock

import pytest

from fleet.tasks._aws_components import (
    ANNOTATION_TARGET_SECRET,
    CLUSTER_LABEL,
    COMPONENTS,
    REGENERATE,
    TARGET_ANNOTATIONS,
    DiscoveryError,
    access_key_name,
    all_iam_targets,
    discover_components,
    iam_targets,
    installer_access_key_name,
    labelled_iam_targets,
    manifests_secret_name,
    raw_secret_name,
)
from tests.unit._aws_fixtures import (
    OPERATORS,
    RENDERING,
    access_key_item,
    access_keys_payload,
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


# ---------------------------------------------------------------------------
# Operator discovery: the target annotations the scaffold writes on each AccessKey
# ---------------------------------------------------------------------------


def _key(comp):
    return comp.access_key.removeprefix("test-cluster-").removesuffix("-access-key")


def _operator_items(cluster="test-cluster"):
    """OPERATORS as labelled AccessKeys, listed in reverse so the result must be sorted."""
    return [
        access_key_item(
            cluster, _key(comp), comp.credentials_request, comp.namespace, comp.secret
        )
        for comp in reversed(OPERATORS)
    ]


def _payload(*items, cluster="test-cluster"):
    """oc get accesskeys -o json: the installer AccessKey (no annotations) plus items."""
    return access_keys_payload(access_key_item(cluster, None), *items)


def test_installer_access_key_name():
    assert installer_access_key_name("c1") == "c1-access-key"


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_query(mock_run):
    mock_run.return_value = _payload(*_operator_items("c1"), cluster="c1")
    discover_components("c1")
    mock_run.assert_called_once_with(
        [
            "oc",
            "get",
            "accesskeys.iam.aws.upbound.io",
            "-l",
            f"{CLUSTER_LABEL}=c1",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_parses_annotated_access_keys(mock_run):
    mock_run.return_value = _payload(*_operator_items())
    found = discover_components("test-cluster")
    # Sorted by access_key (the payload was reversed); raw_secret is the
    # AccessKey's writeConnectionSecretToRef.name
    assert found == OPERATORS
    assert [c.raw_secret for c in found] == [
        "test-cluster-ingress-credentials-raw",
        "test-cluster-machine-api-credentials-raw",
    ]


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_skips_installer_access_key(mock_run):
    mock_run.return_value = _payload(*_operator_items())
    found = discover_components("test-cluster")
    assert len(found) == len(OPERATORS)
    assert installer_access_key_name("test-cluster") not in {
        c.access_key for c in found
    }
    assert "aws-credentials-raw" not in {c.raw_secret for c in found}


@pytest.mark.parametrize("annotated", [True, False])
@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_fails_on_missing_annotation(mock_run, annotated):
    broken = access_key_item("test-cluster", "extra", annotated=annotated)
    if annotated:
        del broken["metadata"]["annotations"][ANNOTATION_TARGET_SECRET]
    mock_run.return_value = _payload(*_operator_items(), broken)
    with pytest.raises(DiscoveryError) as exc:
        discover_components("test-cluster")
    assert "AccessKey test-cluster-extra-access-key lacks target annotations" in str(
        exc.value
    )
    assert REGENERATE in str(exc.value)


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_fails_when_none_annotated(mock_run):
    mock_run.return_value = _payload(cluster="c1")
    with pytest.raises(DiscoveryError) as exc:
        discover_components("c1")
    assert str(exc.value) == (
        f"no operator AccessKeys carry target annotations for c1; {REGENERATE}"
    )


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_fails_on_oc_error(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="denied\n"
    )
    with pytest.raises(DiscoveryError) as exc:
        discover_components("c1")
    assert str(exc.value) == "AccessKey lookup failed for c1: denied"


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_vendored_rendering_matches_contract(mock_run):
    """The scaffold rendering in tests/data is what discovery reads on a real hub."""
    rendering = json.loads(RENDERING.read_text())
    items = {item["metadata"]["name"]: item for item in rendering["items"]}
    cluster = next(iter(items.values()))["metadata"]["labels"][CLUSTER_LABEL]
    installer = installer_access_key_name(cluster)
    assert installer in items

    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout=RENDERING.read_text(), stderr=""
    )
    found = discover_components(cluster)
    assert len(found) == len(items) - 1
    assert installer not in {c.access_key for c in found}
    for comp in found:
        item = items[comp.access_key]
        assert set(TARGET_ANNOTATIONS) <= set(item["metadata"]["annotations"])
        assert comp.raw_secret == item["spec"]["writeConnectionSecretToRef"]["name"]
        assert comp.namespace and comp.secret
