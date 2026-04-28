from unittest import mock

import subprocess

import pytest
import requests

from fleet.tasks.register_keycloak_client import (
    _build_client_urls,
    _build_client_payload,
    main,
)

BASE_ARGV = [
    "prog",
    "--cluster-name",
    "test-cluster",
    "--keycloak-url",
    "https://keycloak.example.com",
    "--keycloak-realm",
    "openshift",
    "--keycloak-admin-secret",
    "keycloak-admin",
    "--base-domain",
    "example.com",
]


def _admin_cred_side_effects(*extra):
    return [
        subprocess.CompletedProcess([], returncode=0, stdout="admin-user", stderr=""),
        subprocess.CompletedProcess([], returncode=0, stdout="admin-pass", stderr=""),
        *extra,
    ]


def _mock_token_resp():
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": "admin-token"}
    return resp


def _mock_realm_resp(status=200):
    resp = mock.Mock()
    resp.status_code = status
    return resp


def _mock_secret_resp(value="client-secret-value"):
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = {"value": value}
    return resp


# --- Unit tests for helper functions ---


def test_build_client_urls():
    home, redirect, post_logout = _build_client_urls(
        "spoke1", "labs.example.com", "RedHat"
    )
    assert home == "https://console-openshift-console.apps.spoke1.labs.example.com"
    assert (
        redirect
        == "https://oauth-openshift.apps.spoke1.labs.example.com/oauth2callback/RedHat"
    )
    assert post_logout == home


def test_build_client_urls_custom_provider():
    _, redirect, _ = _build_client_urls("c1", "d.com", "MyIDP")
    assert redirect.endswith("/oauth2callback/MyIDP")


def test_build_client_payload():
    payload = _build_client_payload(
        "my-cluster",
        "https://console.apps.c.d",
        "https://oauth.apps.c.d/oauth2callback/RedHat",
        "https://console.apps.c.d",
    )
    assert payload["clientId"] == "my-cluster"
    assert payload["publicClient"] is False
    assert payload["clientAuthenticatorType"] == "client-secret"
    assert payload["standardFlowEnabled"] is True
    assert payload["directAccessGrantsEnabled"] is False
    assert payload["implicitFlowEnabled"] is False
    assert payload["serviceAccountsEnabled"] is False
    assert payload["rootUrl"] == "https://console.apps.c.d"
    assert payload["redirectUris"] == ["https://oauth.apps.c.d/oauth2callback/RedHat"]
    assert payload["webOrigins"] == ["/*"]
    assert (
        payload["attributes"]["post.logout.redirect.uris"] == "https://console.apps.c.d"
    )


# --- Integration tests via main() ---


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_register_new_client(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = []

    create_resp = mock.Mock()
    create_resp.status_code = 201
    create_resp.headers = {
        "Location": "https://keycloak.example.com/admin/realms/openshift/clients/new-uuid"
    }

    secret_resp = _mock_secret_resp()

    mock_requests.post.side_effect = [token_resp, create_resp]
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess(
            [], returncode=0, stdout="secret configured", stderr=""
        ),
    )

    with mock.patch("sys.argv", BASE_ARGV):
        main()
    assert mock_run.call_count == 3
    apply_call = mock_run.call_args_list[2]
    cmd = apply_call.args[0]
    assert cmd[0] == "oc"
    assert "apply" in cmd

    create_call = mock_requests.post.call_args_list[1]
    payload = create_call.kwargs["json"]
    assert payload["clientId"] == "test-cluster"
    assert payload["redirectUris"][0].endswith("/oauth2callback/RedHat")
    assert payload["publicClient"] is False


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_register_existing_client_puts_update(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "existing-uuid", "clientId": "test-cluster"}]

    put_resp = mock.Mock()
    put_resp.status_code = 200

    secret_resp = _mock_secret_resp("existing-secret")

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]
    mock_requests.put.return_value = put_resp

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="configured", stderr=""),
    )

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    mock_requests.put.assert_called_once()
    put_call = mock_requests.put.call_args
    assert "existing-uuid" in put_call.args[0]
    payload = put_call.kwargs["json"]
    assert payload["clientId"] == "test-cluster"
    assert payload["redirectUris"][0].endswith("/oauth2callback/RedHat")


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_exact_match_rejects_substring(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [
        {"id": "wrong-uuid", "clientId": "test-cluster-old"},
    ]

    create_resp = mock.Mock()
    create_resp.status_code = 201
    create_resp.headers = {
        "Location": "https://kc.example.com/admin/realms/openshift/clients/new-uuid"
    }

    secret_resp = _mock_secret_resp()

    mock_requests.post.side_effect = [token_resp, create_resp]
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    )

    with mock.patch("sys.argv", BASE_ARGV):
        main()

    assert mock_requests.post.call_count == 2


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

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_realm_not_found_exits(mock_requests, mock_run):
    token_resp = _mock_token_resp()

    realm_resp = mock.Mock()
    realm_resp.status_code = 404

    mock_requests.post.return_value = token_resp
    mock_requests.get.return_value = realm_resp

    mock_run.side_effect = _admin_cred_side_effects()

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_secret_creation_fails(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    put_resp = mock.Mock()
    put_resp.status_code = 200

    secret_resp = _mock_secret_resp("secret-val")

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]
    mock_requests.put.return_value = put_resp

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=1, stdout="", stderr="forbidden"),
    )

    with mock.patch("sys.argv", BASE_ARGV):
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

    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    put_resp = mock.Mock()
    put_resp.status_code = 200

    secret_resp = _mock_secret_resp("client-secret")

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]
    mock_requests.put.return_value = put_resp

    with mock.patch("sys.argv", BASE_ARGV):
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
    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_auth_realm_param(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    put_resp = mock.Mock()
    put_resp.status_code = 200

    secret_resp = _mock_secret_resp()

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]
    mock_requests.put.return_value = put_resp

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    )

    with mock.patch("sys.argv", [*BASE_ARGV, "--auth-realm", "custom-realm"]):
        main()

    token_call = mock_requests.post.call_args
    assert "/realms/custom-realm/" in token_call.args[0]


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_insecure_flag(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = [{"id": "uuid", "clientId": "test-cluster"}]

    put_resp = mock.Mock()
    put_resp.status_code = 200

    secret_resp = _mock_secret_resp()

    mock_requests.post.return_value = token_resp
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]
    mock_requests.put.return_value = put_resp

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    )

    with mock.patch("sys.argv", [*BASE_ARGV, "--insecure"]):
        main()

    for call in mock_requests.post.call_args_list:
        assert call.kwargs.get("verify") is False
    for call in mock_requests.get.call_args_list:
        assert call.kwargs.get("verify") is False
    assert mock_requests.put.call_args.kwargs.get("verify") is False


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_provider_name_in_redirect_uri(mock_requests, mock_run):
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()

    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = []

    create_resp = mock.Mock()
    create_resp.status_code = 201
    create_resp.headers = {"Location": "https://kc/admin/realms/r/clients/new-uuid"}

    secret_resp = _mock_secret_resp()

    mock_requests.post.side_effect = [token_resp, create_resp]
    mock_requests.get.side_effect = [realm_resp, get_resp, secret_resp]

    mock_run.side_effect = _admin_cred_side_effects(
        subprocess.CompletedProcess([], returncode=0, stdout="ok", stderr=""),
    )

    with mock.patch("sys.argv", [*BASE_ARGV, "--provider-name", "CustomIDP"]):
        main()

    create_call = mock_requests.post.call_args_list[1]
    payload = create_call.kwargs["json"]
    assert "/oauth2callback/CustomIDP" in payload["redirectUris"][0]


@mock.patch("fleet.tasks.register_keycloak_client.subprocess.run")
@mock.patch("fleet.tasks.register_keycloak_client.requests")
def test_create_client_returns_fail(mock_requests, mock_run):
    """Test that create with HTTP 500 fails properly and logs error."""
    token_resp = _mock_token_resp()
    realm_resp = _mock_realm_resp()
    get_resp = mock.Mock()
    get_resp.status_code = 200
    get_resp.json.return_value = []

    fail_resp = mock.Mock()
    fail_resp.status_code = 500
    fail_resp.text = "Internal Server Error"

    mock_requests.post.side_effect = [token_resp, fail_resp]
    mock_requests.get.side_effect = [realm_resp, get_resp]

    mock_run.side_effect = _admin_cred_side_effects()

    with mock.patch("sys.argv", BASE_ARGV):
        with pytest.raises(SystemExit, match="1"):
            main()
    assert mock_requests.post.call_count == 2
