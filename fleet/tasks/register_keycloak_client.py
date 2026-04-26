"""Register a Keycloak client for the spoke cluster.

CLI: fleet-register-keycloak-client --cluster-name NAME
     --keycloak-url URL --keycloak-realm REALM
     --keycloak-admin-secret SECRET
Idempotent: checks if client exists, creates or reuses.
Stores creds in Hub Secret. Exits 1 on failure.
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


def _get_admin_token(base_url: str, admin_user: str, admin_pass: str) -> str:
    token_resp = requests.post(
        f"{base_url}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
        },
        timeout=30,
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


def _ensure_client(
    base_url: str, realm: str, cluster: str, headers: dict[str, str]
) -> str:
    get_resp = requests.get(
        f"{base_url}/admin/realms/{realm}/clients?clientId={cluster}",
        headers=headers,
        timeout=30,
    )
    if get_resp.status_code == 200 and get_resp.json():
        return get_resp.json()[0]["id"]

    create_resp = requests.post(
        f"{base_url}/admin/realms/{realm}/clients",
        headers=headers,
        json={
            "clientId": cluster,
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
        },
        timeout=30,
    )
    return create_resp.json()["id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--keycloak-url", required=True)
    parser.add_argument("--keycloak-realm", required=True)
    parser.add_argument("--keycloak-admin-secret", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    base_url = args.keycloak_url.rstrip("/")
    realm = args.keycloak_realm

    admin_user = _read_secret_key(args.keycloak_admin_secret, "username")
    admin_pass = _read_secret_key(args.keycloak_admin_secret, "password")

    token = _get_admin_token(base_url, admin_user, admin_pass)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    client_id = _ensure_client(base_url, realm, cluster, headers)

    secret_resp = requests.get(
        f"{base_url}/admin/realms/{realm}/clients/{client_id}/client-secret",
        headers=headers,
        timeout=30,
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
