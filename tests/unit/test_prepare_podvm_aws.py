from unittest import mock

import binascii
import json
import subprocess

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._podvm_aws import PodVMError
from fleet.tasks.prepare_podvm_aws import main

KUBECONFIG = "/workspace/source/kubeconfig"
FACTS = ("c1-abcde", "us-east-2", "aws-credentials")
NETWORK = ("vpc-1", "subnet-1", ["sg-a", "sg-b"])


def _argv():
    return mock.patch(
        "sys.argv", ["prog", "--cluster-name", "c1", "--spoke-kubeconfig", KUBECONFIG]
    )


def _nodes(**instances):
    """Worker nodes as `oc get nodes -o json` lists them: node name -> instance ID."""
    items = [
        {
            "metadata": {"name": name},
            "spec": {"providerID": f"aws:///us-east-2a/{instance}"},
        }
        for name, instance in instances.items()
    ]
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=json.dumps({"items": items}), stderr=""
    )


@pytest.fixture(autouse=True)
def helpers():
    """Hub facts and every EC2 helper are replaced; the node listing is the only oc call."""
    module = "fleet.tasks.prepare_podvm_aws"
    with (
        mock.patch(f"{module}.cluster_facts", return_value=FACTS) as cluster_facts,
        mock.patch(f"{module}.ec2_client") as ec2_client,
        mock.patch(f"{module}.node_network", return_value=NETWORK) as node_network,
        mock.patch(f"{module}.open_podvm_ports", return_value=6) as open_podvm_ports,
        mock.patch(f"{module}.subprocess.run", return_value=_nodes(a="i-0a")) as run,
    ):
        yield mock.Mock(
            cluster_facts=cluster_facts,
            ec2_client=ec2_client,
            node_network=node_network,
            open_podvm_ports=open_podvm_ports,
            run=run,
        )


def test_prints_the_four_values(helpers, capsys):
    with _argv():
        main()
    assert json.loads(capsys.readouterr().out) == {
        "region": "us-east-2",
        "vpc-id": "vpc-1",
        "subnet-id": "subnet-1",
        "sg-ids": "sg-a,sg-b",
    }
    ec2 = helpers.ec2_client.return_value
    helpers.cluster_facts.assert_called_once_with("c1")
    helpers.ec2_client.assert_called_once_with("c1", "us-east-2", "aws-credentials")
    helpers.run.assert_called_once_with(
        [
            "oc",
            "get",
            "nodes",
            "-l",
            "node-role.kubernetes.io/worker",
            "-o",
            "json",
            f"--kubeconfig={KUBECONFIG}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    helpers.node_network.assert_called_once_with(ec2, "i-0a")
    helpers.open_podvm_ports.assert_called_once_with(ec2, ["sg-a", "sg-b"])


def test_takes_the_first_worker_node_by_name(helpers):
    helpers.run.return_value = _nodes(worker_c="i-0c", worker_a="i-0a", worker_b="i-0b")
    with _argv():
        main()
    helpers.node_network.assert_called_once_with(
        helpers.ec2_client.return_value, "i-0a"
    )


def _assert_fails(helpers, capsys, message):
    """Exit 1, one error line containing message, nothing on stdout."""
    with mock.patch("fleet.tasks.prepare_podvm_aws.error") as mock_error:
        with _argv(), pytest.raises(SystemExit, match="1"):
            main()
    assert len(mock_error.call_args_list) == 1
    assert message in str(mock_error.call_args.args[0])
    assert capsys.readouterr().out == ""


def test_no_worker_node_exits(helpers, capsys):
    helpers.run.return_value = _nodes()
    _assert_fails(helpers, capsys, "no node with role worker on the spoke")
    helpers.node_network.assert_not_called()
    helpers.open_podvm_ports.assert_not_called()


def test_missing_instance_exits_before_any_rule_is_added(helpers, capsys):
    helpers.node_network.side_effect = PodVMError("instance i-0a not found")
    _assert_fails(helpers, capsys, "instance i-0a not found")
    helpers.open_podvm_ports.assert_not_called()


def test_ec2_error_exits(helpers, capsys):
    helpers.node_network.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
        "DescribeInstances",
    )
    _assert_fails(helpers, capsys, "UnauthorizedOperation")


def test_node_listing_failure_exits_with_stderr(helpers, capsys):
    helpers.run.side_effect = subprocess.CalledProcessError(
        1, ["oc", "get", "nodes"], stderr="Unable to connect to the server\n"
    )
    _assert_fails(helpers, capsys, "Unable to connect to the server")
    helpers.node_network.assert_not_called()


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("ClusterDeployment c1 has no infraID (not installed?)"),
        KeyError("aws_access_key_id"),
        binascii.Error("Incorrect padding"),
        BotoCoreError(),
    ],
)
def test_hub_lookup_failure_exits(helpers, capsys, exc):
    helpers.cluster_facts.side_effect = exc
    _assert_fails(helpers, capsys, "Failed to prepare the pod VM network")
    helpers.run.assert_not_called()


def test_node_without_provider_id_exits(helpers, capsys):
    helpers.run.return_value = subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout=json.dumps({"items": [{"metadata": {"name": "a"}, "spec": {}}]}),
        stderr="",
    )
    _assert_fails(helpers, capsys, "providerID")
