from unittest import mock

import base64
import json
import subprocess

import pytest
import yaml

from fleet.tasks._aws_components import COMPONENTS
from fleet.tasks.build_aws_credentials_manifests import main

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


@mock.patch("fleet.tasks.build_aws_credentials_manifests.subprocess.run")
def test_builds_manifest_secret_for_hive(mock_run):
    mock_run.side_effect = [_raw_secret() for _ in COMPONENTS] + [_ok()]
    with _argv():
        main()

    # One read per operator, then a single apply over stdin
    reads = mock_run.call_args_list[: len(COMPONENTS)]
    for call, comp in zip(reads, COMPONENTS):
        assert call.args[0] == [
            "oc",
            "get",
            "secret",
            f"c1-{comp.key}-credentials-raw",
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
    assert len(outer["stringData"]) == len(COMPONENTS)
    for comp in COMPONENTS:
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
    mock_run.side_effect = [_raw_secret() for _ in COMPONENTS] + [_ok()]
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
    mock_run.side_effect = [_raw_secret() for _ in COMPONENTS] + [
        subprocess.CalledProcessError(1, "oc", stderr="denied")
    ]
    with _argv():
        with pytest.raises(SystemExit, match="1"):
            main()
