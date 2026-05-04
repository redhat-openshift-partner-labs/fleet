"""Create a per-cluster cert-manager ClusterIssuer for Let's Encrypt DNS-01.

CLI: fleet-create-cluster-issuer --cluster-name NAME --acme-email EMAIL

Reads AWS credentials from the aws-credentials Secret in the cluster
namespace, creates a Secret in openshift-ingress for cert-manager, and
creates a ClusterIssuer that uses Route53 for DNS-01 validation.

Exit 0 on success, 1 on failure.
"""

import argparse
import base64
import binascii
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--acme-email", default="admin@example.com")
    args = parser.parse_args()

    cluster = args.cluster_name
    acme_email = args.acme_email

    configure("create-cluster-issuer")

    info("=== Creating per-cluster ClusterIssuer ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  acme-email={acme_email}")

    info(f"Reading aws-credentials from ns {cluster}...")
    try:
        access_key_b64 = subprocess.run(
            [
                "oc",
                "get",
                "secret",
                "aws-credentials",
                "-n",
                cluster,
                "-o",
                "jsonpath={.data.aws_access_key_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        info(f"  -> Read aws_access_key_id (b64, bytes: {len(access_key_b64)})")

        secret_key_b64 = subprocess.run(
            [
                "oc",
                "get",
                "secret",
                "aws-credentials",
                "-n",
                cluster,
                "-o",
                "jsonpath={.data.aws_secret_access_key}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        info(f"  -> Read aws_secret_access_key (b64, bytes: {len(secret_key_b64)})")

        access_key = base64.b64decode(access_key_b64).decode()
        secret_key = base64.b64decode(secret_key_b64).decode()
        info("  -> Base64 decoded")
    except (subprocess.CalledProcessError, binascii.Error) as exc:
        error(f"Failed to read aws-credentials: {exc}")
        sys.exit(1)

    secret_name = f"{cluster}-cert-manager-aws"
    info(f"Creating Secret {secret_name} in cert-manager...")
    try:
        dry_run = subprocess.run(
            [
                "oc",
                "create",
                "secret",
                "generic",
                secret_name,
                "-n",
                "cert-manager",
                f"--from-literal=secret_access_key={secret_key}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info("  -> Dry-run YAML generated")

        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=dry_run.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        info(f"  -> Secret {secret_name} created")
    except subprocess.CalledProcessError as exc:
        error(f"Failed to create cert-manager-aws Secret: {exc}")
        sys.exit(1)

    issuer_name = f"letsencrypt-{cluster}"
    issuer_yaml = (
        f"apiVersion: cert-manager.io/v1\n"
        f"kind: ClusterIssuer\n"
        f"metadata:\n"
        f"  name: {issuer_name}\n"
        f"spec:\n"
        f"  acme:\n"
        f"    server: https://acme-v02.api.letsencrypt.org/directory\n"
        f"    email: {acme_email}\n"
        f"    privateKeySecretRef:\n"
        f"      name: {issuer_name}-account-key\n"
        f"    solvers:\n"
        f"      - dns01:\n"
        f"          route53:\n"
        f"            region: us-east-1\n"
        f"            accessKeyID: {access_key}\n"
        f"            secretAccessKeySecretRef:\n"
        f"              name: {secret_name}\n"
        f"              key: secret_access_key\n"
    )
    info(f"Creating ClusterIssuer {issuer_name}...")
    try:
        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=issuer_yaml,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(f"Failed to create ClusterIssuer: {exc}")
        sys.exit(1)
    info(f"ClusterIssuer {issuer_name} created")
