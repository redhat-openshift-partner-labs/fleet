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
import base64
import subprocess
import sys
import textwrap

import requests

from fleet.tasks._env import check_configmap_env, resolve_bool, resolve_required
from fleet.tasks._log import configure, error, info


def _read_secret_key(secret_name: str, key: str) -> str:
    info(f"Reading {key} from secret {secret_name}")
    jsonpath = f"jsonpath={{.data.{key}}}"
    result = subprocess.run(
        ["oc", "get", "secret", secret_name, "-o", jsonpath],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read {key} from secret {secret_name}: {result.stderr}")
        sys.exit(1)
    raw = result.stdout.strip()
    value = base64.b64decode(raw).decode("utf-8")
    info(f"  Got {key} (length: {len(value)})")
    return value


def _build_client_urls(
    cluster_name: str, base_domain: str, provider_name: str
) -> tuple[str, str, str]:
    """Build console, redirect, and logout URLs for the OAuth client."""
    apps = f"apps.{cluster_name}.{base_domain}"
    home_url = f"https://console-openshift-console.{apps}"
    redirect_uri = f"https://oauth-openshift.{apps}/oauth2callback/{provider_name}"
    return home_url, redirect_uri, home_url


def _build_client_payload(
    client_id: str, home_url: str, redirect_uri: str, post_logout_uri: str
) -> dict:
    """Build the Keycloak client registration payload."""
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--keycloak-url", default=None)
    parser.add_argument("--keycloak-realm", default=None)
    parser.add_argument("--keycloak-admin-secret", default=None)
    parser.add_argument("--base-domain", default=None)
    parser.add_argument("--auth-realm", default=None)
    parser.add_argument("--provider-name", default=None)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "register-keycloak-client"
    )
    args.keycloak_url = resolve_required(
        args.keycloak_url, "keycloak-url", "register-keycloak-client"
    )
    args.keycloak_realm = resolve_required(
        args.keycloak_realm, "keycloak-realm", "register-keycloak-client"
    )
    args.keycloak_admin_secret = resolve_required(
        args.keycloak_admin_secret, "keycloak-admin-secret", "register-keycloak-client"
    )
    args.base_domain = resolve_required(
        args.base_domain, "base-domain", "register-keycloak-client"
    )
    args.auth_realm = resolve_required(
        args.auth_realm, "auth-realm", "register-keycloak-client"
    )
    args.provider_name = resolve_required(
        args.provider_name, "provider-name", "register-keycloak-client"
    )
    args.insecure = resolve_bool(args.insecure, "insecure", "register-keycloak-client")

    configure("register-keycloak-client")

    info("=== Registering Keycloak OIDC client ===")
    info("Parameters:")
    for key, value in vars(args).items():
        info(f"  {key}={value}")

    cluster = args.cluster_name
    base_url = args.keycloak_url.rstrip("/")
    realm = args.keycloak_realm
    verify_tls = not args.insecure

    info(f"Reading admin credentials from secret '{args.keycloak_admin_secret}'...")
    admin_user = _read_secret_key(args.keycloak_admin_secret, "username")
    admin_pass = _read_secret_key(args.keycloak_admin_secret, "password")

    token_url = f"{base_url}/realms/{args.auth_realm}/protocol/openid-connect/token"
    info(f"Getting admin token from {token_url}")
    info(f"  admin user: {admin_user}")
    token_resp = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
        },
        timeout=30,
        verify=verify_tls,
    )
    info(f"  -> HTTP {token_resp.status_code}")
    if token_resp.status_code != 200:
        error(
            f"Failed to get Keycloak admin token (HTTP {token_resp.status_code}): {token_resp.text[:200]}"
        )
        sys.exit(1)
    token = token_resp.json()["access_token"]
    info("Admin token obtained")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    realm_url = f"{base_url}/admin/realms/{realm}"
    info(f"Verifying realm '{realm}' at {realm_url}...")
    realm_resp = requests.get(realm_url, headers=headers, timeout=30, verify=verify_tls)
    info(f"  -> HTTP {realm_resp.status_code}")
    if realm_resp.status_code == 404:
        error(f"Realm '{realm}' not found at {realm_url}")
        sys.exit(1)

    client_url = f"{base_url}/admin/realms/{realm}/clients"
    info(f"Checking for existing client at {client_url}...")
    existing_resp = requests.get(
        client_url,
        params={"clientId": cluster, "first": "0", "max": "1"},
        headers=headers,
        timeout=30,
        verify=verify_tls,
    )
    info(f"  -> HTTP {existing_resp.status_code}")
    existing_uuid = None
    if existing_resp.status_code == 200 and existing_resp.json():
        for c in existing_resp.json():
            if c["clientId"] == cluster:
                existing_uuid = c["id"]
                break

    apps_domain = f"apps.{cluster}.{args.base_domain}"
    if existing_uuid:
        info(f"Existing client found: {existing_uuid}")
        home_url = f"https://console-openshift-console.{apps_domain}"
        redirect_uri = (
            f"https://oauth-openshift.{apps_domain}/oauth2callback/{args.provider_name}"
        )
        payload = {
            "clientId": cluster,
            "name": cluster,
            "protocol": "openid-connect",
            "publicClient": False,
            "redirectUris": [redirect_uri],
            "rootUrl": home_url,
            "baseUrl": home_url,
            "enabled": True,
        }
        update_url = f"{client_url}/{existing_uuid}"
        info(f"Updating client at {update_url}...")
        put_resp = requests.put(
            update_url, json=payload, headers=headers, timeout=30, verify=verify_tls
        )
        info(f"  -> HTTP {put_resp.status_code}")
        client_url = existing_uuid
    else:
        info("No existing client, creating new...")
        home_url = f"https://console-openshift-console.{apps_domain}"
        redirect_uri = (
            f"https://oauth-openshift.{apps_domain}/oauth2callback/{args.provider_name}"
        )
        payload = {
            "clientId": cluster,
            "name": cluster,
            "protocol": "openid-connect",
            "publicClient": False,
            "redirectUris": [redirect_uri],
            "rootUrl": home_url,
            "baseUrl": home_url,
            "enabled": True,
        }
        info(
            f"  payload: clientId={cluster}, redirectURI={redirect_uri}, rootUrl={home_url}"
        )
        create_resp = requests.post(
            client_url, headers=headers, json=payload, timeout=30, verify=verify_tls
        )
        info(f"  -> HTTP {create_resp.status_code}")
        if create_resp.status_code not in (201, 200, 204):
            error(f"Failed to create client: {create_resp.text[:200]}")
            sys.exit(1)
        client_url = create_resp.headers.get("Location", "").rstrip("/").split("/")[-1]
        info(f"  Created client: {client_url}")

    secret_url = f"{base_url}/admin/realms/{realm}/clients/{client_url}/client-secret"
    info(f"Retrieving client secret from {secret_url}...")
    secret_resp = requests.get(
        secret_url, headers=headers, timeout=30, verify=verify_tls
    )
    info(f"  -> HTTP {secret_resp.status_code}")
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
        error(f"Failed to create client secret: {result.stderr}")
        sys.exit(1)

    info("Client secret stored in hub Secret")
