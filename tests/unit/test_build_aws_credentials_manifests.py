from unittest import mock

import base64
import json
import subprocess

import pytest
import yaml

from fleet.tasks._aws_components import DiscoveryError
from fleet.tasks.build_aws_credentials_manifests import main
from tests.unit._aws_fixtures import OPERATORS, PEER_PODS

KEY_ID, SECRET = "AKIAEXAMPLEKEYID", "s3cr3t/value+with=chars"


def _raw_secret(key_id=KEY_ID, secret=SECRET):
    data = {
        "username": base64.b64encode(key_id.encode()).decode(),
        "password": base64.b64encode(secret.encode()).decode(),
    }
    return subprocess.CompletedProcess(
        [], returncode=0, stdout=json.dumps({"data": data}), stderr=""
    )


def _ok():
    return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")


def _argv():
    return mock.patch("sys.argv", ["prog", "--cluster-name", "c1"])


@pytest.fixture(autouse=True)
def discovery():
    """Every test sees OPERATORS and the post-provision PEER_PODS from discovery.

    The oc sequences hold only the Secret reads of OPERATORS and the apply: a read of the
    peer-pods raw Secret would exhaust them.
    """
    with mock.patch(
        "fleet.tasks.build_aws_credentials_manifests.discover_components",
        return_value=OPERATORS + [PEER_PODS],
    ) as discover:
        yield discover


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_builds_manifest_secret_for_hive(mock_run):
    mock_run.side_effect = [_raw_secret() for _ in OPERATORS] + [_ok()]
    with _argv():
        main()

    # One read per discovered operator (raw Secret name taken as discovered), then a
    # single apply over stdin
    reads = mock_run.call_args_list[: len(OPERATORS)]
    for call, comp in zip(reads, OPERATORS):
        assert call.args[0] == [
            "oc",
            "get",
            "secret",
            comp.raw_secret,
            "-n",
            "c1",
            "-o",
            "json",
        ]
    apply = mock_run.call_args_list[-1]
    assert apply.args[0] == ["oc", "apply", "-f", "-"]

    outer = json.loads(apply.kwargs["input"])
    assert outer["kind"] == "Secret"
    assert outer["metadata"] == {
        "name": "c1-cloud-credentials-manifests",
        "namespace": "c1",
    }
    assert len(outer["stringData"]) == len(OPERATORS)
    for comp in OPERATORS:
        manifest = yaml.safe_load(
            outer["stringData"][f"cco-secret-{comp.namespace}-{comp.secret}.yaml"]
        )
        assert manifest["metadata"] == {
            "name": comp.secret,
            "namespace": comp.namespace,
        }
        assert manifest["stringData"] == {
            "aws_access_key_id": KEY_ID,
            "aws_secret_access_key": SECRET,
        }


@mock.patch("fleet.tasks.build_aws_credentials_manifests.info")
@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_secrets_never_on_argv_or_logged(mock_run, mock_info):
    mock_run.side_effect = [_raw_secret() for _ in OPERATORS] + [_ok()]
    with _argv():
        main()
    for call in mock_run.call_args_list:
        assert SECRET not in " ".join(call.args[0])
        assert KEY_ID not in " ".join(call.args[0])
    logged = " ".join(str(c.args[0]) for c in mock_info.call_args_list)
    assert SECRET not in logged and KEY_ID not in logged


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_read_failure_exits(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "oc", stderr="forbidden")
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_empty_credential_exits(mock_run):
    mock_run.side_effect = [_raw_secret(key_id="")]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_malformed_secret_exits(mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="{}", stderr="")
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_apply_failure_exits(mock_run):
    mock_run.side_effect = [_raw_secret() for _ in OPERATORS] + [
        subprocess.CalledProcessError(1, "oc", stderr="denied")
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.build_aws_credentials_manifests.info")
@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_logs_raw_secret_and_credentials_request(mock_run, mock_info, discovery):
    mock_run.side_effect = [_raw_secret() for _ in OPERATORS] + [_ok()]
    with _argv():
        main()
    discovery.assert_called_once_with("c1")
    logged = [str(c.args[0]) for c in mock_info.call_args_list]
    for comp in OPERATORS:
        assert f"Reading {comp.raw_secret} ({comp.credentials_request})..." in logged


@mock.patch("fleet.tasks.build_aws_credentials_manifests.error")
@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_discovery_failure_exits(mock_run, mock_error, discovery):
    message = "no operator AccessKeys carry target annotations for c1; regenerate"
    discovery.side_effect = DiscoveryError(message)
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()
    mock_run.assert_not_called()
    assert [str(c.args[0]) for c in mock_error.call_args_list] == [
        f"Failed to read operator credentials: {message}"
    ]


@mock.patch("fleet.tasks.build_aws_credentials_manifests.info")
@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_post_provision_credential_is_left_out(mock_run, mock_info):
    """The peer-pods namespace does not exist at install time; a post-provision task delivers it."""
    mock_run.side_effect = [_raw_secret() for _ in OPERATORS] + [_ok()]
    with _argv():
        main()

    argvs = [call.args[0] for call in mock_run.call_args_list]
    assert not [argv for argv in argvs if PEER_PODS.raw_secret in argv]
    outer = json.loads(mock_run.call_args_list[-1].kwargs["input"])
    assert sorted(outer["stringData"]) == sorted(
        f"cco-secret-{comp.namespace}-{comp.secret}.yaml" for comp in OPERATORS
    )
    assert not [key for key in outer["stringData"] if PEER_PODS.secret in key]
    logged = [str(c.args[0]) for c in mock_info.call_args_list]
    assert (
        f"Skipping {PEER_PODS.raw_secret} ({PEER_PODS.credentials_request}): "
        "delivered post-provision"
    ) in logged
    assert (
        f"Applying Secret c1-cloud-credentials-manifests with {len(OPERATORS)} manifest(s)..."
        in logged
    )
