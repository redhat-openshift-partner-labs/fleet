from unittest import mock

import pytest

from fleet.tasks._test_vcluster import OWNER_LABEL
from fleet.tasks.delete_test_vcluster import main
from tests.unit._fake_hub import FakeHub, found, unreadable

NAME = "test-vc"
NAMESPACE = "test-ns"
ARGV = ["prog", "--cluster-name", NAME, "--namespace", NAMESPACE]

# The ManagedCluster is gone at the first poll after its deletion.
GONE = (("oc", "get", "managedcluster", NAME), 1, "", "not found")
NO_VCLUSTER_NAMESPACE = (("oc", "get", "namespace", NAMESPACE), 1, "", "not found")
OWNED_NAMESPACE = found("namespace", NAME, labels={OWNER_LABEL: NAME})
TEST_CLUSTER = found("managedcluster", NAME, labels={"cloud": "vcluster"})

DELETE_MANAGEDCLUSTER = ["oc", "delete", "managedcluster", NAME]
DELETE_ROUTE = ["oc", "delete", "route", NAME]
VCLUSTER_DELETE = ["vcluster", "delete", NAME, "-n", NAMESPACE]
DELETE_VCLUSTER_NAMESPACE = ["oc", "delete", "namespace", NAMESPACE]
DELETE_NAMESPACE = ["oc", "delete", "namespace", NAME]
DELETE_CRONJOB = ["oc", "delete", "cronjob", NAME]
DELETE_SECRET = ["oc", "delete", "secret", f"{NAME}-spoke-kubeconfig"]


def failing(prefix):
    return (prefix, 1, "", "error")


def run(*rules, exit_code=None):
    """Run the tool against a fake hub; returns the hub with the recorded commands."""
    hub = FakeHub(*rules)
    with mock.patch("subprocess.run", hub), mock.patch("time.sleep"):
        with mock.patch("sys.argv", ARGV):
            if exit_code is None:
                main()
            else:
                with pytest.raises(SystemExit) as raised:
                    main()
                assert raised.value.code == exit_code
    return hub


def prefixes(hub):
    """The first words of each changing command, without its options."""
    known = [
        DELETE_MANAGEDCLUSTER,
        DELETE_ROUTE,
        VCLUSTER_DELETE,
        DELETE_VCLUSTER_NAMESPACE,
        DELETE_NAMESPACE,
        DELETE_CRONJOB,
        DELETE_SECRET,
    ]
    result = []
    for call in hub.changes():
        match = [prefix for prefix in known if call[: len(prefix)] == prefix]
        assert match, f"unexpected command {call}"
        result.append(match[0])
    return result


def test_deletes_every_resource_of_a_test_run():
    hub = run(TEST_CLUSTER, GONE, OWNED_NAMESPACE)
    assert prefixes(hub) == [
        DELETE_MANAGEDCLUSTER,
        DELETE_ROUTE,
        VCLUSTER_DELETE,
        DELETE_NAMESPACE,
        DELETE_CRONJOB,
        DELETE_SECRET,
    ]


def test_each_deletion_names_its_namespace_and_ignores_a_missing_object():
    hub = run(TEST_CLUSTER, GONE, OWNED_NAMESPACE)
    changes = {tuple(call[:4]): call for call in hub.changes()}
    route = changes[("oc", "delete", "route", NAME)]
    cronjob = changes[("oc", "delete", "cronjob", NAME)]
    secret = changes[("oc", "delete", "secret", f"{NAME}-spoke-kubeconfig")]
    namespace = changes[("oc", "delete", "namespace", NAME)]
    assert route[-2:] == ["-n", NAMESPACE]
    assert cronjob[-2:] == ["-n", "default"]
    assert secret[-2:] == ["-n", "openshift-pipelines"]
    assert "--timeout=300s" in namespace
    for call in (route, cronjob, secret, namespace):
        assert "--ignore-not-found=true" in call


@pytest.mark.parametrize(
    "rule",
    [
        found("clusterdeployment", NAME, NAME),
        found("managedcluster", NAME, labels={"cloud": "Amazon"}),
        found("managedcluster", NAME),
        unreadable("clusterdeployment", NAME, NAME),
        unreadable("managedcluster", NAME),
    ],
)
def test_changes_nothing_when_the_name_is_not_of_a_test(rule):
    hub = run(rule, GONE, OWNED_NAMESPACE, exit_code=1)
    assert hub.changes() == []


def test_runs_without_any_resource_on_the_hub():
    # The finally task also runs when load-config failed and nothing was created.
    hub = run(GONE, NO_VCLUSTER_NAMESPACE)
    assert prefixes(hub) == [DELETE_MANAGEDCLUSTER, DELETE_CRONJOB, DELETE_SECRET]


def test_waits_for_the_managedcluster_to_be_gone():
    hub = FakeHub(OWNED_NAMESPACE)
    polls = iter([0, 0, 1])

    def answer(cmd, **kwargs):
        if cmd == ["oc", "get", "managedcluster", NAME]:
            hub.calls.append(cmd)
            return mock.Mock(returncode=next(polls), stdout="", stderr="")
        return FakeHub.__call__(hub, cmd, **kwargs)

    with mock.patch("subprocess.run", answer), mock.patch("time.sleep") as sleep:
        with mock.patch("sys.argv", ARGV):
            main()
    assert sleep.call_count == 2
    assert hub.calls.count(["oc", "get", "managedcluster", NAME]) == 3


def test_proceeds_when_the_managedcluster_stays():
    hub = run(OWNED_NAMESPACE)
    assert hub.calls.count(["oc", "get", "managedcluster", NAME]) == 60
    assert DELETE_SECRET in prefixes(hub)


def test_falls_back_to_the_namespace_when_vcluster_delete_fails():
    hub = run(GONE, failing(VCLUSTER_DELETE), found("secret", f"vc-{NAME}", NAMESPACE))
    assert prefixes(hub) == [
        DELETE_MANAGEDCLUSTER,
        DELETE_ROUTE,
        VCLUSTER_DELETE,
        DELETE_VCLUSTER_NAMESPACE,
        DELETE_CRONJOB,
        DELETE_SECRET,
    ]


def test_keeps_the_namespace_when_it_holds_no_vcluster():
    # vcluster delete fails because create-test-vcluster never created one.
    hub = run(GONE, failing(VCLUSTER_DELETE))
    assert DELETE_VCLUSTER_NAMESPACE not in prefixes(hub)


def test_fails_when_the_vcluster_cannot_be_looked_up():
    hub = run(
        GONE,
        failing(VCLUSTER_DELETE),
        unreadable("secret", f"vc-{NAME}", NAMESPACE),
        exit_code=1,
    )
    assert DELETE_VCLUSTER_NAMESPACE not in prefixes(hub)
    assert DELETE_SECRET in prefixes(hub)


def test_keeps_a_namespace_that_no_test_created():
    hub = run(GONE, found("namespace", NAME, labels={"team": "payments"}))
    assert DELETE_NAMESPACE not in prefixes(hub)
    assert DELETE_SECRET in prefixes(hub)


def test_fails_when_the_namespace_cannot_be_read():
    hub = run(GONE, unreadable("namespace", NAME), exit_code=1)
    assert DELETE_NAMESPACE not in prefixes(hub)
    assert DELETE_SECRET in prefixes(hub)


@pytest.mark.parametrize(
    "command",
    [
        DELETE_MANAGEDCLUSTER,
        DELETE_ROUTE,
        DELETE_VCLUSTER_NAMESPACE,
        DELETE_NAMESPACE,
        DELETE_CRONJOB,
        DELETE_SECRET,
    ],
)
def test_attempts_every_deletion_and_exits_1_when_one_fails(command, capsys):
    hub = run(
        GONE,
        OWNED_NAMESPACE,
        failing(VCLUSTER_DELETE),
        found("secret", f"vc-{NAME}", NAMESPACE),
        failing(command),
        exit_code=1,
    )
    assert prefixes(hub) == [
        DELETE_MANAGEDCLUSTER,
        DELETE_ROUTE,
        VCLUSTER_DELETE,
        DELETE_VCLUSTER_NAMESPACE,
        DELETE_NAMESPACE,
        DELETE_CRONJOB,
        DELETE_SECRET,
    ]
    assert f"Not deleted: {command[2]} {command[3]}" in capsys.readouterr().err
