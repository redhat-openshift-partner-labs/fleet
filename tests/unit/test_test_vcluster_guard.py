from unittest import mock

import pytest

from fleet.tasks._test_vcluster import (
    ABSENT,
    FOREIGN,
    OWNED,
    OWNER_LABEL,
    has_vcluster,
    namespace_state,
    refusal,
)
from tests.unit._fake_hub import FakeHub, found, unreadable

NAME = "test-vc"


def _run(hub, function, *args):
    with mock.patch("subprocess.run", hub):
        return function(*args)


def test_no_refusal_when_the_hub_holds_nothing_of_that_name():
    hub = FakeHub()
    assert _run(hub, refusal, NAME) is None
    assert hub.changes() == []


def test_no_refusal_for_the_managedcluster_of_a_test():
    hub = FakeHub(found("managedcluster", NAME, labels={"cloud": "vcluster"}))
    assert _run(hub, refusal, NAME) is None


def test_refusal_when_a_clusterdeployment_has_the_name():
    hub = FakeHub(found("clusterdeployment", NAME, NAME))
    reason = _run(hub, refusal, NAME)
    assert reason == f"ClusterDeployment {NAME} exists in namespace {NAME}"
    # The ManagedCluster is not read after the first reason.
    assert len(hub.calls) == 1


@pytest.mark.parametrize("labels", [{}, {"cloud": "Amazon"}, {"tier": "base"}])
def test_refusal_when_the_managedcluster_is_not_of_a_test(labels):
    hub = FakeHub(found("managedcluster", NAME, labels=labels))
    reason = _run(hub, refusal, NAME)
    assert reason == f"ManagedCluster {NAME} does not carry the label cloud=vcluster"


@pytest.mark.parametrize(
    ("kind", "namespace"), [("clusterdeployment", NAME), ("managedcluster", None)]
)
def test_refusal_when_the_hub_cannot_be_read(kind, namespace):
    hub = FakeHub(unreadable(kind, NAME, namespace))
    assert _run(hub, refusal, NAME) == f"cannot read {kind} {NAME}: forbidden"


def test_namespace_state_absent():
    assert _run(FakeHub(), namespace_state, NAME) == ABSENT


def test_namespace_state_owned():
    hub = FakeHub(found("namespace", NAME, labels={OWNER_LABEL: NAME}))
    assert _run(hub, namespace_state, NAME) == OWNED


@pytest.mark.parametrize("labels", [{}, {OWNER_LABEL: "another-test"}])
def test_namespace_state_foreign(labels):
    hub = FakeHub(found("namespace", NAME, labels=labels))
    assert _run(hub, namespace_state, NAME) == FOREIGN


def test_namespace_state_raises_when_the_hub_cannot_be_read():
    hub = FakeHub(unreadable("namespace", NAME))
    with pytest.raises(RuntimeError, match="cannot read namespace test-vc"):
        _run(hub, namespace_state, NAME)


def test_has_vcluster_reads_the_name_of_the_secret_only():
    hub = FakeHub(found("secret", f"vc-{NAME}", "test-ns"))
    assert _run(hub, has_vcluster, NAME, "test-ns") is True
    # -o name: the kubeconfig of the Secret is not read.
    assert hub.calls[0][-2:] == ["-o", "name"]
    assert _run(FakeHub(), has_vcluster, NAME, "test-ns") is False
