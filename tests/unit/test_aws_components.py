import base64
import json
import subprocess
from unittest import mock

import pytest

from fleet.tasks._aws_components import (
    ANNOTATION_DELIVERY,
    ANNOTATION_TARGET_SECRET,
    CLUSTER_LABEL,
    DELIVERY_POST_PROVISION,
    PEER_PODS_SECRET,
    REGENERATE,
    TARGET_ANNOTATIONS,
    TIER_COCO,
    DiscoveryError,
    all_iam_targets,
    discover_components,
    iam_targets,
    install_credentials,
    installer_access_key_name,
    labelled_iam_targets,
    manifests_secret_name,
    post_provision_credentials,
    read_raw_credentials,
)
from tests.unit._aws_fixtures import (
    COCO_RENDERING,
    OPERATORS,
    PEER_PODS,
    RENDERING,
    access_key_item,
    access_keys_payload,
)


def test_resource_names():
    assert manifests_secret_name("c1") == "c1-cloud-credentials-manifests"


def test_iam_targets_are_the_fixed_names_only():
    """Operator resources are found by label; only these six keep fixed names."""
    assert iam_targets("c1") == [
        "userpolicyattachment.iam/c1-policy-attachment",
        "accesskey.iam/c1-access-key",
        "policy.iam/c1-openshift4installerpolicy",
        "user.iam/c1-ocp-installer",
        "role.iam/c1-master-role",
        "role.iam/c1-worker-role",
    ]


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
def test_labelled_targets_raise_on_oc_failure(mock_run):
    """A failed lookup is not an empty cluster: nothing may be deleted on it."""
    mock_run.return_value = _get("", returncode=1)
    with pytest.raises(DiscoveryError) as exc:
        labelled_iam_targets("c1")
    assert str(exc.value) == "IAM label lookup failed for c1: denied"


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_all_targets_propagate_lookup_failure(mock_run):
    mock_run.return_value = _get("", returncode=1)
    with pytest.raises(DiscoveryError):
        all_iam_targets("c1")


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


def _peer_pods_item(cluster="test-cluster", delivery=PEER_PODS.delivery):
    """PEER_PODS as a labelled AccessKey."""
    return access_key_item(
        cluster,
        "peer-pods",
        PEER_PODS.credentials_request,
        PEER_PODS.namespace,
        PEER_PODS.secret,
        delivery=delivery,
    )


def _rendering(path):
    """A vendored scaffold rendering as the oc answer."""
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=path.read_text(), stderr=""
    )


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


@pytest.mark.parametrize("path", [RENDERING, COCO_RENDERING])
@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_vendored_rendering_matches_contract(mock_run, path):
    """The scaffold renderings in tests/data are what discovery reads on a real hub."""
    rendering = json.loads(path.read_text())
    items = {item["metadata"]["name"]: item for item in rendering["items"]}
    cluster = next(iter(items.values()))["metadata"]["labels"][CLUSTER_LABEL]
    installer = installer_access_key_name(cluster)
    assert installer in items

    mock_run.return_value = _rendering(path)
    found = discover_components(cluster)
    assert len(found) == len(items) - 1
    assert installer not in {c.access_key for c in found}
    for comp in found:
        item = items[comp.access_key]
        assert set(TARGET_ANNOTATIONS) <= set(item["metadata"]["annotations"])
        assert comp.raw_secret == item["spec"]["writeConnectionSecretToRef"]["name"]
        assert comp.namespace and comp.secret


# ---------------------------------------------------------------------------
# Delivery: where the pipeline delivers a credential (install manifests or post-provision)
# ---------------------------------------------------------------------------


def test_scaffold_contract_strings():
    """Strings the scaffold writes; a change here needs the same change there."""
    assert ANNOTATION_DELIVERY == "openshiftpartnerlabs.com/delivery"
    assert DELIVERY_POST_PROVISION == "post-provision"
    assert TIER_COCO == "coco"
    assert PEER_PODS_SECRET == "peer-pods-secret"


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_reads_delivery(mock_run):
    mock_run.return_value = _payload(*_operator_items(), _peer_pods_item())
    found = discover_components("test-cluster")
    assert found == OPERATORS + [PEER_PODS]
    assert [c.delivery for c in found] == [None, None, DELIVERY_POST_PROVISION]


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_treats_empty_delivery_as_absent(mock_run):
    mock_run.return_value = _payload(
        *_operator_items(), access_key_item("test-cluster", "extra", delivery="")
    )
    found = discover_components("test-cluster")
    assert [c.delivery for c in found] == [None, None, None]


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_fails_on_unknown_delivery(mock_run):
    """An image that predates a delivery value must not treat it as an install credential."""
    mock_run.return_value = _payload(
        *_operator_items(), _peer_pods_item(delivery="at-install")
    )
    with pytest.raises(DiscoveryError) as exc:
        discover_components("test-cluster")
    assert str(exc.value) == (
        "AccessKey test-cluster-peer-pods-access-key has unknown delivery 'at-install'; "
        "update the pipeline image"
    )


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_discover_components_fails_without_an_install_credential(mock_run):
    mock_run.return_value = _payload(_peer_pods_item())
    with pytest.raises(DiscoveryError) as exc:
        discover_components("test-cluster")
    assert str(exc.value) == (
        f"no operator AccessKeys carry target annotations for test-cluster; {REGENERATE}"
    )


def test_install_credentials_leave_out_post_provision():
    assert install_credentials(OPERATORS + [PEER_PODS]) == OPERATORS
    assert install_credentials([PEER_PODS]) == []


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_post_provision_credentials_query(mock_run):
    mock_run.return_value = _payload(cluster="c1")
    assert post_provision_credentials("c1") == []
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
def test_post_provision_credentials_empty_for_base_rendering(mock_run):
    mock_run.return_value = _rendering(RENDERING)
    assert post_provision_credentials("fixture") == []


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_post_provision_credentials_of_coco_rendering(mock_run):
    mock_run.return_value = _rendering(COCO_RENDERING)
    found = post_provision_credentials("fixture")
    assert found == [
        PEER_PODS._replace(
            raw_secret="fixture-peer-pods-credentials-raw",
            access_key="fixture-peer-pods-access-key",
        )
    ]


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_post_provision_credentials_sorted_and_tolerant(mock_run):
    """A post-provision AccessKey that lacks a target annotation is left out, not an error."""
    broken = access_key_item("test-cluster", "broken", delivery=PEER_PODS.delivery)
    del broken["metadata"]["annotations"][ANNOTATION_TARGET_SECRET]
    bare = access_key_item(
        "test-cluster", "bare", annotated=False, delivery=PEER_PODS.delivery
    )
    other = access_key_item(
        "test-cluster", "another", delivery=PEER_PODS.delivery, secret="other-secret"
    )
    mock_run.return_value = _payload(
        _peer_pods_item(), *_operator_items(), broken, bare, other
    )
    found = post_provision_credentials("test-cluster")
    assert [c.access_key for c in found] == [
        "test-cluster-another-access-key",
        "test-cluster-peer-pods-access-key",
    ]
    assert found[1] == PEER_PODS


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_post_provision_credentials_fail_on_oc_error(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="denied\n"
    )
    with pytest.raises(DiscoveryError) as exc:
        post_provision_credentials("c1")
    assert str(exc.value) == "AccessKey lookup failed for c1: denied"


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_coco_rendering_has_one_post_provision_credential(mock_run):
    """Pins the delivery annotation key and value against what the scaffold renders."""
    mock_run.return_value = _rendering(COCO_RENDERING)
    found = discover_components("fixture")
    assert len(found) == 7
    post = [c for c in found if c.delivery is not None]
    assert [(c.delivery, c.secret) for c in post] == [
        (DELIVERY_POST_PROVISION, PEER_PODS_SECRET)
    ]
    assert len(install_credentials(found)) == 6


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_base_rendering_has_install_credentials_only(mock_run):
    mock_run.return_value = _rendering(RENDERING)
    found = discover_components("fixture")
    assert [c.delivery for c in found] == [None] * 6
    assert install_credentials(found) == found


# ---------------------------------------------------------------------------
# Raw credential Secrets (Crossplane AccessKey connection Secret: username/password)
# ---------------------------------------------------------------------------

KEY_ID, SECRET = "AKIAEXAMPLEKEYID", "s3cr3t/value+with=chars"


def _raw_secret(key_id=KEY_ID, secret=SECRET):
    data = {
        "username": base64.b64encode(key_id.encode()).decode(),
        "password": base64.b64encode(secret.encode()).decode(),
    }
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=json.dumps({"data": data}), stderr=""
    )


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_read_raw_credentials(mock_run):
    mock_run.return_value = _raw_secret()
    assert read_raw_credentials("c1", PEER_PODS) == (KEY_ID, SECRET)
    mock_run.assert_called_once_with(
        ["oc", "get", "secret", PEER_PODS.raw_secret, "-n", "c1", "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )


@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_read_raw_credentials_propagates_oc_failure(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="forbidden")
    with pytest.raises(subprocess.CalledProcessError):
        read_raw_credentials("c1", OPERATORS[0])


@pytest.mark.parametrize("empty", ["key_id", "secret"])
@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_read_raw_credentials_rejects_empty_values(mock_run, empty):
    mock_run.return_value = _raw_secret(**{empty: ""})
    with pytest.raises(ValueError) as exc:
        read_raw_credentials("c1", OPERATORS[0])
    assert str(exc.value) == (
        f"Secret {OPERATORS[0].raw_secret} has an empty username or password"
    )


@pytest.mark.parametrize(
    "stdout", ["{}", '{"data": null}', '{"data": {"username": ""}}']
)
@mock.patch("fleet.tasks._aws_components.subprocess.run")
def test_read_raw_credentials_rejects_malformed_secret(mock_run, stdout):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=0, stdout=stdout, stderr=""
    )
    with pytest.raises(KeyError):
        read_raw_credentials("c1", OPERATORS[0])
