"""Create a GitHub deployment and set its status to success."""

import argparse
import base64
import json
import subprocess
import sys
import time

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from fleet.tasks._log import configure, error, info


def _sign_jwt(pem_bytes: bytes, app_id: str, now: float) -> str:
    loaded = serialization.load_pem_private_key(pem_bytes, password=None)
    if not isinstance(loaded, rsa.RSAPrivateKey):
        raise TypeError("Expected RSA private key")
    key: rsa.RSAPrivateKey = loaded

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
    ).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {"iss": app_id, "iat": int(now) - 60, "exp": int(now) + 600}
        ).encode()
    ).rstrip(b"=")

    signing_input = header + b"." + payload
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")

    return (signing_input + b"." + sig_b64).decode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--pipeline-run-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--github-app-id", required=True)
    parser.add_argument("--github-app-installation-id", required=True)
    parser.add_argument("--github-app-key-secret", required=True)
    args = parser.parse_args()

    configure("create-deployment-status")

    info("=== Creating GitHub deployment status ===")
    info("Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  pipeline-run-id={args.pipeline_run_id}")
    info(f"  repo={args.repo}")
    info(f"  github-app-id={args.github_app_id}")
    info(f"  github-app-installation-id={args.github_app_installation_id}")
    info(f"  github-app-key-secret={args.github_app_key_secret}")

    result = subprocess.run(
        [
            "oc",
            "get",
            f"secret/{args.github_app_key_secret}",
            "-n",
            "openshift-pipelines",
            "-o",
            "jsonpath={.data.private-key}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read GitHub App private key: {result.stderr}")
        sys.exit(1)

    pem_bytes = base64.b64decode(result.stdout)
    info("  -> Private key loaded")

    now = time.time()
    jwt_token = _sign_jwt(pem_bytes, args.github_app_id, now)
    info("  -> JWT signed")

    jwt_headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }

    token_resp = requests.post(
        f"https://api.github.com/app/installations/{args.github_app_installation_id}/access_tokens",
        headers=jwt_headers,
        timeout=30,
    )
    if token_resp.status_code != 201:
        error(
            f"Failed to get installation token (HTTP {token_resp.status_code}): {token_resp.text[:200]}"
        )
        sys.exit(1)

    installation_token = token_resp.json()["token"]
    info("  -> Installation token acquired")

    token_headers = {
        "Authorization": f"token {installation_token}",
        "Accept": "application/vnd.github+json",
    }

    deploy_resp = requests.post(
        f"https://api.github.com/repos/{args.repo}/deployments",
        headers=token_headers,
        json={
            "ref": "main",
            "environment": "deprovision",
            "auto_merge": False,
            "required_contexts": [],
            "payload": {
                "cluster_id": args.cluster_name,
                "pipeline_run_id": args.pipeline_run_id,
            },
        },
        timeout=30,
    )
    if deploy_resp.status_code != 201:
        error(
            f"Failed to create deployment (HTTP {deploy_resp.status_code}): {deploy_resp.text[:200]}"
        )
        sys.exit(1)

    deploy_id = deploy_resp.json()["id"]
    info(f"  -> Deployment created (id={deploy_id})")

    status_resp = requests.post(
        f"https://api.github.com/repos/{args.repo}/deployments/{deploy_id}/statuses",
        headers=token_headers,
        json={"state": "success"},
        timeout=30,
    )
    if status_resp.status_code != 201:
        error(
            f"Failed to create deployment status (HTTP {status_resp.status_code}): {status_resp.text[:200]}"
        )
        sys.exit(1)

    info("  -> Deployment status set to success")
    info("Done")
