from unittest import mock

import base64
import json
import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

from fleet.tasks.create_deployment_status import _sign_jwt, main

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--pipeline-run-id",
    "run-abc123",
    "--repo",
    "redhat-openshift-partner-labs/fleet-clusters",
    "--github-app-id",
    "12345",
    "--github-app-installation-id",
    "67890",
    "--github-app-key-secret",
    "fleet-github-app-key",
]

FAKE_PEM = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQo="  # placeholder b64


def _mock_oc_secret_success():
    return subprocess.CompletedProcess([], returncode=0, stdout=FAKE_PEM, stderr="")


def _mock_oc_secret_fail():
    return subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="secret not found"
    )


def _mock_token_resp():
    resp = mock.Mock()
    resp.status_code = 201
    resp.json.return_value = {"token": "ghs_fake_installation_token"}
    return resp


def _mock_deployment_resp(deploy_id=42):
    resp = mock.Mock()
    resp.status_code = 201
    resp.json.return_value = {"id": deploy_id}
    return resp


def _mock_status_resp():
    resp = mock.Mock()
    resp.status_code = 201
    resp.json.return_value = {"id": 1, "state": "success"}
    return resp


def _mock_fail_resp(status=422, text="Unprocessable Entity"):
    resp = mock.Mock()
    resp.status_code = status
    resp.text = text
    return resp


@mock.patch("fleet.tasks.create_deployment_status.time.time", return_value=1700000000)
@mock.patch("fleet.tasks.create_deployment_status._sign_jwt")
@mock.patch("fleet.tasks.create_deployment_status.requests")
@mock.patch("fleet.tasks.create_deployment_status.subprocess.run")
def test_success(mock_run, mock_requests, mock_sign, mock_time):
    mock_run.return_value = _mock_oc_secret_success()
    mock_sign.return_value = "fake.jwt.token"

    mock_requests.post.side_effect = [
        _mock_token_resp(),
        _mock_deployment_resp(42),
        _mock_status_resp(),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    assert mock_run.call_count == 1
    cmd = mock_run.call_args.args[0]
    assert "fleet-github-app-key" in " ".join(cmd)

    assert mock_requests.post.call_count == 3

    token_call = mock_requests.post.call_args_list[0]
    assert "/installations/67890/access_tokens" in token_call.args[0]

    deploy_call = mock_requests.post.call_args_list[1]
    assert "/deployments" in deploy_call.args[0]
    payload = deploy_call.kwargs["json"]
    assert payload["environment"] == "deprovision"
    assert payload["payload"]["cluster_id"] == "test-cluster"
    assert payload["payload"]["pipeline_run_id"] == "run-abc123"
    assert payload["auto_merge"] is False
    assert payload["required_contexts"] == []

    status_call = mock_requests.post.call_args_list[2]
    assert "/deployments/42/statuses" in status_call.args[0]
    assert status_call.kwargs["json"]["state"] == "success"


@mock.patch("fleet.tasks.create_deployment_status.subprocess.run")
def test_secret_read_fails(mock_run):
    mock_run.return_value = _mock_oc_secret_fail()

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_deployment_status.time.time", return_value=1700000000)
@mock.patch("fleet.tasks.create_deployment_status._sign_jwt")
@mock.patch("fleet.tasks.create_deployment_status.requests")
@mock.patch("fleet.tasks.create_deployment_status.subprocess.run")
def test_token_exchange_fails(mock_run, mock_requests, mock_sign, mock_time):
    mock_run.return_value = _mock_oc_secret_success()
    mock_sign.return_value = "fake.jwt.token"

    mock_requests.post.return_value = _mock_fail_resp(401, "Bad credentials")

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_deployment_status.time.time", return_value=1700000000)
@mock.patch("fleet.tasks.create_deployment_status._sign_jwt")
@mock.patch("fleet.tasks.create_deployment_status.requests")
@mock.patch("fleet.tasks.create_deployment_status.subprocess.run")
def test_deployment_create_fails(mock_run, mock_requests, mock_sign, mock_time):
    mock_run.return_value = _mock_oc_secret_success()
    mock_sign.return_value = "fake.jwt.token"

    mock_requests.post.side_effect = [
        _mock_token_resp(),
        _mock_fail_resp(422, "Validation failed"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.create_deployment_status.time.time", return_value=1700000000)
@mock.patch("fleet.tasks.create_deployment_status._sign_jwt")
@mock.patch("fleet.tasks.create_deployment_status.requests")
@mock.patch("fleet.tasks.create_deployment_status.subprocess.run")
def test_status_create_fails(mock_run, mock_requests, mock_sign, mock_time):
    mock_run.return_value = _mock_oc_secret_success()
    mock_sign.return_value = "fake.jwt.token"

    mock_requests.post.side_effect = [
        _mock_token_resp(),
        _mock_deployment_resp(42),
        _mock_fail_resp(500, "Internal Server Error"),
    ]

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_sign_jwt():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )

    token = _sign_jwt(pem_bytes, "12345", 1700000000.0)

    parts = token.split(".")
    assert len(parts) == 3

    def _pad(s):
        return s + "=" * (-len(s) % 4)

    header = json.loads(base64.urlsafe_b64decode(_pad(parts[0])))
    assert header == {"alg": "RS256", "typ": "JWT"}

    payload = json.loads(base64.urlsafe_b64decode(_pad(parts[1])))
    assert payload["iss"] == "12345"
    assert payload["iat"] == 1700000000 - 60
    assert payload["exp"] == 1700000000 + 600

    sig_bytes = base64.urlsafe_b64decode(_pad(parts[2]))
    signing_input = (parts[0] + "." + parts[1]).encode()
    public_key = private_key.public_key()
    public_key.verify(sig_bytes, signing_input, padding.PKCS1v15(), hashes.SHA256())


def test_sign_jwt_rejects_non_rsa_key():
    from cryptography.hazmat.primitives.asymmetric import ec

    ec_key = ec.generate_private_key(ec.SECP256R1())
    pem_bytes = ec_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    with pytest.raises(TypeError, match="Expected RSA private key"):
        _sign_jwt(pem_bytes, "12345", 1700000000.0)


def test_missing_required_args():
    with mock.patch("sys.argv", ["prog"]):
        with pytest.raises(SystemExit, match="2"):
            main()
