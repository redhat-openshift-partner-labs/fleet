"""Register a Keycloak OIDC client for the spoke cluster.

CLI: fleet-register-keycloak-client --cluster-name NAME
     --keycloak-url URL --keycloak-realm REALM --base-domain DOMAIN
     --keycloak-admin-secret SECRET [--auth-realm REALM] [--insecure]
     [--provider-name NAME]

Idempotent: creates the client if missing, updates to desired state if
it already exists. Stores client-id and client-secret as a Hub Secret.
Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

import requests


def _read_secret_key(secret_name: str, key: str) -> str:
    result = subprocess.run(
        [
            "oc",
            "get",
            "secret",
            secret_name,
            "-o",
            f"jsonpath={{.data.{key}}}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"Failed to read {key} from {secret_name}: {result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout.strip()


def _build_client_urls(
    cluster_name: str, base_domain: str, provider_name: str
) -> tuple[str, str, str]:
    apps = f"apps.{cluster_name}.{base_domain}"
    home_url = f"https://console-openshift-console.{apps}"
    redirect_uri = f"https://oauth-openshift.{apps}/oauth2callback/{provider_name}"
    return home_url, redirect_uri, home_url


def _build_client_payload(
    client_id: str, home_url: str, redirect_uri: str, post_logout_uri: str
) -> dict:
    return {
        "clientId": client_id,
        "name": client_id,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "implicitFlowEnabled": False,
        "serviceAccountsEnabled": False,
        "rootUrl": home_url,
        "baseUrl": home_url,
        "redirectUris": [redirect_uri],
        "webOrigins": ["/*"],
        "attributes": {"post.logout.redirect.uris": post_logout_uri},
        "enabled": True,
    }


def _get_admin_token(
    base_url: str,
    admin_user: str,
    admin_pass: str,
    auth_realm: str = "master",
    verify_tls: bool = True,
) -> str:
    token_resp = requests.post(
        f"{base_url}/realms/{auth_realm}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
        },
        timeout=30,
        verify=verify_tls,
    )
    try:
        token_resp.raise_for_status()
    except requests.HTTPError:
        print(
            f"Failed to get Keycloak admin token: {token_resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    return token_resp.json()["access_token"]


def _verify_realm(
    base_url: str, realm: str, headers: dict[str, str], verify_tls: bool = True
) -> None:
    resp = requests.get(
        f"{base_url}/admin/realms/{realm}",
        headers=headers,
        timeout=30,
        verify=verify_tls,
    )
    if resp.status_code == 404:
        print(f"Realm '{realm}' does not exist", file=sys.stderr)
        sys.exit(1)


def _ensure_client(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    base_url: str,
    realm: str,
    cluster: str,
    headers: dict[str, str],
    base_domain: str,
    provider_name: str = "RedHat",
    verify_tls: bool = True,
) -> str:
    home_url, redirect_uri, post_logout_uri = _build_client_urls(
        cluster, base_domain, provider_name
    )
    payload = _build_client_payload(cluster, home_url, redirect_uri, post_logout_uri)

    get_resp = requests.get(
        f"{base_url}/admin/realms/{realm}/clients",
        params={"clientId": cluster, "first": "0", "max": "1"},
        headers=headers,
        timeout=30,
        verify=verify_tls,
    )

    existing_uuid = None
    if get_resp.status_code == 200 and get_resp.json():
        for c in get_resp.json():
            if c["clientId"] == cluster:
                existing_uuid = c["id"]
                break

    if existing_uuid:
        requests.put(
            f"{base_url}/admin/realms/{realm}/clients/{existing_uuid}",
            json={**payload, "id": existing_uuid},
            headers=headers,
            timeout=30,
            verify=verify_tls,
        )
        return existing_uuid

    create_resp = requests.post(
        f"{base_url}/admin/realms/{realm}/clients",
        headers=headers,
        json=payload,
        timeout=30,
        verify=verify_tls,
    )
    return create_resp.headers.get("Location", "").rstrip("/").split("/")[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--keycloak-url", required=True)
    parser.add_argument("--keycloak-realm", required=True)
    parser.add_argument("--keycloak-admin-secret", required=True)
    parser.add_argument("--base-domain", required=True)
    parser.add_argument("--auth-realm", default="master")
    parser.add_argument("--provider-name", default="RedHat")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    cluster = args.cluster_name
    base_url = args.keycloak_url.rstrip("/")
    realm = args.keycloak_realm
    verify_tls = not args.insecure

    admin_user = _read_secret_key(args.keycloak_admin_secret, "username")
    admin_pass = _read_secret_key(args.keycloak_admin_secret, "password")

    token = _get_admin_token(
        base_url, admin_user, admin_pass, args.auth_realm, verify_tls
    )
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    _verify_realm(base_url, realm, headers, verify_tls)

    client_id = _ensure_client(
        base_url,
        realm,
        cluster,
        headers,
        args.base_domain,
        args.provider_name,
        verify_tls,
    )

    secret_resp = requests.get(
        f"{base_url}/admin/realms/{realm}/clients/{client_id}/client-secret",
        headers=headers,
        timeout=30,
        verify=verify_tls,
    )
    client_secret_value = secret_resp.json()["value"]

    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {cluster}-keycloak-client
        type: Opaque
        stringData:
          client-id: {cluster}
          client-secret: {client_secret_value}
    """)

    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to create client secret: {result.stderr}", file=sys.stderr)
        sys.exit(1)
