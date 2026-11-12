import argparse
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
import yaml

from fleet.tasks._aws_components import (
    CLUSTER_LABEL,
    PEER_PODS_SECRET,
    REGENERATE,
    DiscoveryError,
)
from fleet.tasks.apply_coco_workloads import (
    CAA_DAEMONSET,
    FEATURE_GATES_CONFIGMAP,
    KATACONFIG,
    OSC_NAMESPACE,
    OSC_PACKAGE,
    PEER_PODS_CONFIGMAP,
    RUNTIME_CLASS,
    apply_object,
    main,
    peer_pods_config,
    peer_pods_credential,
    wait_for_kataconfig,
)
from tests.unit._aws_fixtures import OPERATORS, PEER_PODS

MODULE = "fleet.tasks.apply_coco_workloads"
WORKLOADS = Path(__file__).parent.parent.parent / "workloads" / "coco"
KUBECONFIG = "/workspace/source/kubeconfig"
SOURCE_DIR = "/workspace/source/workloads/coco"
KEY_ID, SECRET = "AKIAEXAMPLEKEYID", "s3cr3t/value+with=chars"


def _argv(instance_type="m6a.large"):
    return mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--source-dir",
            SOURCE_DIR,
            "--spoke-kubeconfig",
            KUBECONFIG,
            "--podvm-instance-type",
            instance_type,
            "--region",
            "us-east-2",
            "--vpc-id",
            "vpc-1",
            "--subnet-id",
            "subnet-1",
            "--sg-ids",
            "sg-a,sg-b",
            "--ami-id",
            "ami-1",
        ],
    )


def _ok(stdout=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


def _fail(stderr="connection refused"):
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr=stderr)


def _kataconfig(in_progress="False", nodes=3, ready=3, failed=()):
    return _ok(
        json.dumps(
            {
                "status": {
                    "conditions": [{"type": "InProgress", "status": in_progress}],
                    "kataNodes": {
                        "nodeCount": nodes,
                        "readyNodeCount": ready,
                        "failedToInstall": list(failed),
                    },
                }
            }
        )
    )


# ---------------------------------------------------------------------------
# Manifests in workloads/coco and the names the task waits for
# ---------------------------------------------------------------------------


def test_manifests_match_the_module_constants():
    objects = {}
    for path in sorted(WORKLOADS.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            objects[doc["kind"]] = doc
    assert objects["Namespace"]["metadata"]["name"] == OSC_NAMESPACE
    assert objects["ConfigMap"]["metadata"] == {
        "name": FEATURE_GATES_CONFIGMAP,
        "namespace": OSC_NAMESPACE,
    }
    assert objects["ConfigMap"]["data"] == {"confidential": "true"}
    assert objects["OperatorGroup"]["metadata"]["namespace"] == OSC_NAMESPACE
    assert objects["OperatorGroup"]["spec"]["targetNamespaces"] == [OSC_NAMESPACE]
    subscription = objects["Subscription"]
    assert subscription["metadata"] == {"name": OSC_PACKAGE, "namespace": OSC_NAMESPACE}
    assert subscription["spec"] == {
        "channel": "stable",
        "name": OSC_PACKAGE,
        "source": "redhat-operators",
        "sourceNamespace": "openshift-marketplace",
        "installPlanApproval": "Automatic",
    }
    assert objects["KataConfig"]["metadata"] == {"name": KATACONFIG}
    assert objects["KataConfig"]["spec"] == {"enablePeerPods": True, "logLevel": "info"}
    assert objects["Kustomization"]["resources"] == [
        "namespace.yaml",
        "feature-gates.yaml",
        "subscription.yaml",
        "kataconfig.yaml",
    ]


def test_operator_names():
    """Names fixed by the sandboxed containers operator."""
    assert PEER_PODS_CONFIGMAP == "peer-pods-cm"
    assert CAA_DAEMONSET == "osc-caa-ds"
    assert RUNTIME_CLASS == "kata-remote"


# ---------------------------------------------------------------------------
# peer-pods credential and ConfigMap values
# ---------------------------------------------------------------------------


@mock.patch(f"{MODULE}.discover_components")
def test_peer_pods_credential(mock_discover):
    mock_discover.return_value = OPERATORS + [PEER_PODS]
    assert peer_pods_credential("test-cluster") == PEER_PODS
    mock_discover.assert_called_once_with("test-cluster")


@pytest.mark.parametrize(
    "extra, found",
    [
        ([], 0),
        # post-provision, but another target Secret
        ([PEER_PODS._replace(secret="other-secret")], 0),
        # the target Secret name, but delivered by the install manifests
        ([PEER_PODS._replace(delivery=None)], 0),
        ([PEER_PODS, PEER_PODS._replace(access_key="test-cluster-second")], 2),
    ],
)
@mock.patch(f"{MODULE}.discover_components")
def test_peer_pods_credential_must_be_exactly_one(mock_discover, extra, found):
    mock_discover.return_value = OPERATORS + extra
    with pytest.raises(DiscoveryError) as exc:
        peer_pods_credential("test-cluster")
    assert str(exc.value) == (
        f"expected 1 peer-pods credential for test-cluster, found {found}; {REGENERATE}"
    )


def test_peer_pods_config():
    args = argparse.Namespace(
        podvm_instance_type="m6a.large",
        region="us-east-2",
        vpc_id="vpc-1",
        subnet_id="subnet-1",
        sg_ids="sg-a,sg-b",
        ami_id="ami-1",
    )
    assert peer_pods_config("test-cluster", args) == {
        "CLOUD_PROVIDER": "aws",
        "VXLAN_PORT": "9000",
        "PROXY_TIMEOUT": "8m",
        "PODVM_INSTANCE_TYPE": "m6a.large",
        "PODVM_INSTANCE_TYPES": "m6a.large",
        "PODVM_AMI_ID": "ami-1",
        "AWS_REGION": "us-east-2",
        "AWS_SUBNET_ID": "subnet-1",
        "AWS_VPC_ID": "vpc-1",
        "AWS_SG_IDS": "sg-a,sg-b",
        "TAGS": f"{CLUSTER_LABEL}=test-cluster",
        "PEERPODS_LIMIT_PER_NODE": "10",
        "ROOT_VOLUME_SIZE": "6",
        "DISABLECVM": "false",
    }


# ---------------------------------------------------------------------------
# apply_object: objects built by the task go to oc on stdin
# ---------------------------------------------------------------------------


@mock.patch(f"{MODULE}.subprocess.run")
def test_apply_object(mock_run):
    mock_run.return_value = _ok("configmap/peer-pods-cm created")
    obj = {"kind": "ConfigMap", "metadata": {"name": "peer-pods-cm"}, "data": {}}
    assert apply_object(obj, KUBECONFIG) is True
    mock_run.assert_called_once_with(
        ["oc", "apply", "-f", "-", f"--kubeconfig={KUBECONFIG}"],
        input=json.dumps(obj),
        capture_output=True,
        text=True,
    )


@mock.patch(f"{MODULE}.error")
@mock.patch(f"{MODULE}.subprocess.run")
def test_apply_object_failure(mock_run, mock_error):
    mock_run.return_value = _fail("forbidden")
    obj = {"kind": "Secret", "metadata": {"name": "peer-pods-secret"}}
    assert apply_object(obj, KUBECONFIG) is False
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [
        "Failed to apply Secret/peer-pods-secret: forbidden"
    ]


# ---------------------------------------------------------------------------
# wait_for_kataconfig
# ---------------------------------------------------------------------------


@pytest.fixture
def clock():
    """time on the task module: sleep advances monotonic, nothing really waits."""
    with mock.patch(f"{MODULE}.time") as fake:
        now = [0.0]
        fake.monotonic.side_effect = lambda: now[0]
        fake.sleep.side_effect = lambda seconds: now.__setitem__(0, now[0] + seconds)
        yield fake


def _get(kind, name, *scope):
    return ["oc", "get", kind, name, *scope, "-o", "name", f"--kubeconfig={KUBECONFIG}"]


@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_ready_on_the_third_poll(mock_run, clock):
    mock_run.side_effect = [
        _kataconfig(in_progress="True", ready=0),
        _kataconfig(in_progress="True", ready=2),
        _kataconfig(),
        _ok(f"daemonset.apps/{CAA_DAEMONSET}"),
        _ok(f"runtimeclass.node.k8s.io/{RUNTIME_CLASS}"),
    ]
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 5400) is True
    assert [c.args[0] for c in clock.sleep.call_args_list] == [30, 30]
    poll = mock.call(
        [
            "oc",
            "get",
            "kataconfig",
            KATACONFIG,
            "-o",
            "json",
            f"--kubeconfig={KUBECONFIG}",
        ],
        capture_output=True,
        text=True,
    )
    assert mock_run.call_args_list == [
        poll,
        poll,
        poll,
        mock.call(
            _get("daemonset", CAA_DAEMONSET, "-n", OSC_NAMESPACE),
            capture_output=True,
            text=True,
        ),
        mock.call(_get("runtimeclass", RUNTIME_CLASS), capture_output=True, text=True),
    ]


@pytest.mark.parametrize(
    "not_ready",
    [
        _fail(),  # the spoke API restarts while control-plane nodes reboot
        _ok("not json"),
        _ok("{}"),  # no status yet
        _ok(json.dumps({"status": {"conditions": [], "kataNodes": None}})),
        _kataconfig(nodes=0, ready=0),  # no node counted yet
        _kataconfig(in_progress="False", ready=2),
    ],
)
@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_not_ready_answers_are_tolerated(mock_run, clock, not_ready):
    mock_run.side_effect = [
        _kataconfig(in_progress="True", ready=1),
        not_ready,
        _kataconfig(),
        _ok(),
        _ok(),
    ]
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 5400) is True
    assert clock.sleep.call_count == 2


@mock.patch(f"{MODULE}.error")
@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_failed_node_returns_at_once(mock_run, mock_error, clock):
    mock_run.side_effect = [_kataconfig(in_progress="True", ready=1, failed=["w-2"])]
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 5400) is False
    clock.sleep.assert_not_called()
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [
        f"KataConfig {KATACONFIG} failed to install on: w-2"
    ]


@mock.patch(f"{MODULE}.error")
@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_timeout(mock_run, mock_error, clock):
    mock_run.return_value = _kataconfig(in_progress="True", ready=1)
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 90) is False
    # Polls at 0, 30, 60 and 90 s
    assert mock_run.call_count == 4
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [
        f"Timed out after 90s waiting for KataConfig {KATACONFIG}"
    ]


@pytest.mark.parametrize("missing", ["daemonset", "runtimeclass"])
@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_waits_for_daemonset_and_runtime_class(mock_run, clock, missing):
    first_round = (
        [_kataconfig(), _fail("not found")]
        if missing == "daemonset"
        else [_kataconfig(), _ok(), _fail("not found")]
    )
    mock_run.side_effect = first_round + [_kataconfig(), _ok(), _ok()]
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 5400) is True
    assert clock.sleep.call_count == 1


@mock.patch(f"{MODULE}.subprocess.run")
def test_kataconfig_timeout_while_the_daemonset_is_missing(mock_run, clock):
    mock_run.side_effect = lambda argv, **_: (
        _kataconfig() if "kataconfig" in argv else _fail("not found")
    )
    assert wait_for_kataconfig(KATACONFIG, KUBECONFIG, 60) is False


# ---------------------------------------------------------------------------
# main: order on the spoke and failure handling
# ---------------------------------------------------------------------------


@pytest.fixture
def spoke(clock):
    """Hub lookups and the imported helpers are replaced; oc sees the stdin applies and the polls.

    steps records what reaches the spoke, in order: manifest file names, Kind/name of stdin
    applies, and the CSV wait.
    """
    steps = []

    def apply_manifest(path, kubeconfig):
        assert kubeconfig == KUBECONFIG
        steps.append(Path(path).name)
        return path not in failing

    def wait_for_csv(namespace, pattern, kubeconfig, timeout):
        assert (namespace, pattern, kubeconfig, timeout) == (
            OSC_NAMESPACE,
            OSC_PACKAGE,
            KUBECONFIG,
            900,
        )
        steps.append("csv")
        return "csv" not in failing

    def run(argv, **kwargs):
        if argv[:4] == ["oc", "apply", "-f", "-"]:
            obj = json.loads(kwargs["input"])
            step = f"{obj['kind']}/{obj['metadata']['name']}"
            steps.append(step)
            return _fail("denied") if step in failing else _ok()
        if "kataconfig" in argv:
            return _kataconfig(failed=["w-1"] if "kataconfig" in failing else [])
        return _ok()

    failing = set()
    with (
        mock.patch(
            f"{MODULE}.discover_components", return_value=OPERATORS + [PEER_PODS]
        ) as discover,
        mock.patch(
            f"{MODULE}.read_raw_credentials", return_value=(KEY_ID, SECRET)
        ) as read,
        mock.patch(
            f"{MODULE}.check_operator_catalog", return_value=(True, "available")
        ) as catalog,
        mock.patch(f"{MODULE}.apply_manifest", side_effect=apply_manifest),
        mock.patch(f"{MODULE}.wait_for_csv", side_effect=wait_for_csv),
        mock.patch(f"{MODULE}.subprocess.run", side_effect=run) as oc,
        mock.patch(f"{MODULE}.info") as info,
        mock.patch(f"{MODULE}.error") as error,
    ):
        yield mock.Mock(
            steps=steps,
            failing=failing,
            discover=discover,
            read=read,
            catalog=catalog,
            oc=oc,
            info=info,
            error=error,
        )


ALL_STEPS = [
    "namespace.yaml",
    f"Secret/{PEER_PODS_SECRET}",
    "feature-gates.yaml",
    f"ConfigMap/{PEER_PODS_CONFIGMAP}",
    "subscription.yaml",
    "csv",
    "kataconfig.yaml",
]


def _stdin_objects(spoke):
    return {
        f"{obj['kind']}/{obj['metadata']['name']}": obj
        for obj in (
            json.loads(call.kwargs["input"])
            for call in spoke.oc.call_args_list
            if "input" in call.kwargs
        )
    }


def test_applies_in_order(spoke):
    with _argv():
        main()
    assert spoke.steps == ALL_STEPS
    spoke.catalog.assert_called_once_with(
        OSC_PACKAGE, "stable", "redhat-operators", KUBECONFIG
    )
    spoke.discover.assert_called_once_with("test-cluster")
    spoke.read.assert_called_once_with("test-cluster", PEER_PODS)
    spoke.error.assert_not_called()


def test_secret_goes_to_oc_on_stdin_only(spoke):
    with _argv():
        main()
    secret = _stdin_objects(spoke)[f"Secret/{PEER_PODS_SECRET}"]
    assert secret == {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": PEER_PODS.secret, "namespace": PEER_PODS.namespace},
        "type": "Opaque",
        "stringData": {"AWS_ACCESS_KEY_ID": KEY_ID, "AWS_SECRET_ACCESS_KEY": SECRET},
    }
    for call in spoke.oc.call_args_list:
        assert KEY_ID not in " ".join(call.args[0])
        assert SECRET not in " ".join(call.args[0])
    logged = " ".join(
        str(c.args[0]) for c in spoke.info.call_args_list + spoke.error.call_args_list
    )
    assert KEY_ID not in logged and SECRET not in logged


def test_peer_pods_configmap_carries_the_config(spoke):
    with _argv("c6a.xlarge"):
        main()
    configmap = _stdin_objects(spoke)[f"ConfigMap/{PEER_PODS_CONFIGMAP}"]
    assert configmap["metadata"] == {
        "name": PEER_PODS_CONFIGMAP,
        "namespace": OSC_NAMESPACE,
    }
    assert len(configmap["data"]) == 14
    assert "INITDATA" not in configmap["data"]
    assert configmap["data"]["PODVM_INSTANCE_TYPE"] == "c6a.xlarge"
    assert configmap["data"]["AWS_SG_IDS"] == "sg-a,sg-b"


def test_empty_instance_type_exits_before_any_call(spoke):
    with _argv(""), pytest.raises(SystemExit, match="1"):
        main()
    spoke.catalog.assert_not_called()
    spoke.discover.assert_not_called()
    spoke.oc.assert_not_called()
    assert spoke.steps == []
    assert [str(c.args[0]) for c in spoke.error.call_args_list] == [
        f"podvm-instance-type is empty for test-cluster; {REGENERATE}"
    ]


def test_catalog_unavailable_exits_before_the_namespace(spoke):
    spoke.catalog.return_value = (False, "not available from any catalog")
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    spoke.discover.assert_not_called()
    assert spoke.steps == []
    assert [str(c.args[0]) for c in spoke.error.call_args_list] == [
        "OpenShift sandboxed containers operator is unavailable: "
        "not available from any catalog"
    ]


@pytest.mark.parametrize(
    "extra", [[], [PEER_PODS, PEER_PODS._replace(access_key="test-cluster-second")]]
)
def test_zero_or_two_peer_pods_credentials_exit(spoke, extra):
    spoke.discover.return_value = OPERATORS + extra
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    spoke.read.assert_not_called()
    assert spoke.steps == []
    assert len(spoke.error.call_args_list) == 1
    assert "expected 1 peer-pods credential" in str(spoke.error.call_args.args[0])


def test_unreadable_raw_secret_exits(spoke):
    spoke.read.side_effect = subprocess.CalledProcessError(
        1, ["oc", "get", "secret"], stderr="forbidden\n"
    )
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert spoke.steps == []
    assert len(spoke.error.call_args_list) == 1
    assert "forbidden" in str(spoke.error.call_args.args[0])


@pytest.mark.parametrize("failed", [step for step in ALL_STEPS if step != "csv"])
def test_failed_apply_exits_at_that_step(spoke, failed):
    spoke.failing.add(f"{SOURCE_DIR}/{failed}" if failed.endswith(".yaml") else failed)
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert spoke.steps == ALL_STEPS[: ALL_STEPS.index(failed) + 1]


def test_csv_wait_failure_exits(spoke):
    spoke.failing.add("csv")
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert spoke.steps == ALL_STEPS[: ALL_STEPS.index("csv") + 1]


def test_kataconfig_wait_failure_exits(spoke):
    spoke.failing.add("kataconfig")
    with _argv(), pytest.raises(SystemExit, match="1"):
        main()
    assert spoke.steps == ALL_STEPS
    assert "failed to install on: w-1" in str(spoke.error.call_args.args[0])
