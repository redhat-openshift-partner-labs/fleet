from unittest import mock

import subprocess

import pytest
import requests

from fleet.tasks.register_keycloak_client import main


def _admin_cred_side_effects(*extra):
    return [
        subprocess.CompletedProcess([], returncode=0, stdout="admin-user", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="admin-pass", stderr=""),
        *extra,
    ]


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_register_new_client(mock_requests, mock_run):
    token_resp = mock.Mock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "admin-token"}

    get_resp = mock.Mock()
    get_resp.status_code = 404

    create_resp = mock.Mock()
    create_resp.status_code = 201
    create_resp.json.return_value = {
        "id": "client-uuid",
        "secret": "client-secret-value",
    }

    secret_resp = mock.Mock()
    secret_resp.status_code = 200
    secret_resp.json.return_value = {"value": "client-secret-value"}

    mock_requests.post.side_effect = [token_resp, create_resp]
    mock_requests.get.side_effect = [get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess(
            [], returncode=0, stdout="secret configured", stderr=""
        ),
    )

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        main()
    assert mock_run.call_count == 3
    apply_call = mock_run.call_args_list[2]
    cmd = apply_call.args[0]
    assert cmd[0] == "oc"
    assert "apply" in cmd


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_register_existing_client(mock_requests, mock_run):
    token_resp = mock.Mock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "admin-token"}

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "existing-uuid", "clientId": "test-cluster"}]

    secret_resp = mock.Mock()
    secret_resp.status_code = 200
    secret_resp.json.return_value = {"value": "existing-secret"}

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
    )

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        main()
    mock_requests.post.assert_called_once()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_keycloak_token_fails(mock_requests, mock_run):
    mock_requests.HTTPError = requests.HTTPError

    token_resp = mock.Mock()
    token_resp.status_code = 401
    token_resp.text = "unauthorized"
    token_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")

    mock_requests.post.return_value = token_resp

    mock_run.side_effect = _admin_cred_side_effects()

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_secret_creation_fails(mock_requests, mock_run):
    token_resp = mock.Mock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "admin-token"}

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    secret_resp = mock.Mock()
    secret_resp.status_code = 200
    secret_resp.json.return_value = {"value": "secret-val"}

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    )

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_reads_admin_creds_from_hub_secret(mock_requests, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess([], returncode=0, stdout="admin-user", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="admin-pass", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
    ]

    token_resp = mock.Mock()
    token_resp.status_code = 200
    token_resp.json.return_value = {"access_token": "admin-token"}

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    secret_resp = mock.Mock()
    secret_resp.status_code = 200
    secret_resp.json.return_value = {"value": "client-secret"}

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [get_resp, secret_resp]

    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        main()
    first_call = mock_run.call_args_list[0]
    cmd = first_call.args[0]
    assert "keycloak-admin" in " ".join(cmd)


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_admin_cred_read_fails(mock_requests, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        [], returncode=1, stdout="", stderr="not found"
    )
    with mock.patch(
        "sys.argv",
        [
            "prog",
            "--cluster-name",
            "test-cluster",
            "--keycloak-url",
            "https://keycloak.example.com",
            "--keycloak-realm",
            "openshift",
            "--keycloak-admin-secret",
            "keycloak-admin",
        ],
    ):
        with pytest.raises(SystemExit, match="1"):
            main()
