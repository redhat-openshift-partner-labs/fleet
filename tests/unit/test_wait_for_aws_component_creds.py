from unittest import mock

import subprocess

import pytest

from fleet.tasks._aws_components import COMPONENTS, raw_secret_name
from fleet.tasks.wait_for_aws_component_creds import main

RAW_SECRETS = [raw_secret_name("test-cluster", c.key) for c in COMPONENTS]


def _ok(stdout=""):
    return subprocess.CompletedProcess([], returncode=0, stdout=stdout, stderr="")


def _missing():
    return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="not found")


def test_raw_secret_names():
    assert RAW_SECRETS == [
        "test-cluster-machine-api-credentials-raw",
        "test-cluster-cco-iam-ro-credentials-raw",
        "test-cluster-image-registry-credentials-raw",
        "test-cluster-ingress-credentials-raw",
        "test-cluster-cncc-credentials-raw",
        "test-cluster-ebs-csi-credentials-raw",
    ]


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_all_secrets_found_immediately(mock_run, mock_sleep):
    mock_run.return_value = _ok()
    with mock.patch("sys.argv", ["prog", "--cluster-name", "test-cluster"]):
        main()
    mock_sleep.assert_not_called()
    mock_run.assert_called_once_with(
        ["oc", "get", "secret", *RAW_SECRETS, "-n", "test-cluster", "-o", "name"],
        capture_output=True,
        text=True,
    )


@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_found_after_retry(mock_run, mock_sleep):
    mock_run.side_effect = [_missing(), _ok()]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--timeout-seconds", "30"],
    ):
        main()
    mock_sleep.assert_called_once_with(10)


@mock.patch("fleet.tasks.wait_for_aws_component_creds.error")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.time.sleep")
@mock.patch("fleet.tasks.wait_for_aws_component_creds.subprocess.run")
def test_timeout_reports_missing_secrets_and_access_keys(
    mock_run, mock_sleep, mock_error
):
    present = f"secret/{RAW_SECRETS[0]}\n"
    mock_run.side_effect = [
        _missing(),  # poll
        _ok(present),  # which secrets exist
        _ok("NAME READY\nkey False\n"),  # AccessKey diagnostics
    ]
    with mock.patch(
        "sys.argv",
        ["prog", "--cluster-name", "test-cluster", "--timeout-seconds", "10"],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_sleep.call_count == 1
    messages = " ".join(str(c.args[0]) for c in mock_error.call_args_list)
    assert RAW_SECRETS[1] in messages
    assert RAW_SECRETS[0] not in messages
    diag = mock_run.call_args_list[2].args[0]
    assert diag[:3] == ["oc", "get", "accesskey.iam.aws.upbound.io"]
    assert "test-cluster-machine-api-access-key" in diag
