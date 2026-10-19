"""Build the Hive install-manifests Secret carrying per-operator AWS credentials (scoped clusters).

CLI: fleet-build-aws-credentials-manifests --cluster-name NAME
Reads each <cluster>-<operator>-credentials-raw Secret (Crossplane AccessKey: username/password)
and writes Secret <cluster>-cloud-credentials-manifests in namespace {cluster}. Each key is a
Secret manifest for the operator's target namespace/name, which Hive adds to the install
manifests via ClusterDeployment.spec.provisioning.manifestsSecretRef (credentialsMode Manual).
Secret values go through stdin only and are never logged. Exits 1 on any failure.
"""

import argparse
import base64
import binascii
import json
import subprocess
import sys

import yaml

from fleet.tasks._aws_components import (
    COMPONENTS,
    Component,
    manifests_secret_name,
    raw_secret_name,
)
from fleet.tasks._log import configure, error, info


def _read_credentials(cluster: str, comp: Component) -> tuple[str, str]:
    name = raw_secret_name(cluster, comp.key)
    result = subprocess.run(
        ["oc", "get", "secret", name, "-n", cluster, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout).get("data") or {}
    key_id = base64.b64decode(data["username"]).decode()
    secret = base64.b64decode(data["password"]).decode()
    if not key_id or not secret:
        raise ValueError(f"Secret {name} has an empty username or password")
    return key_id, secret


def _operator_manifest(comp: Component, key_id: str, secret: str) -> str:
    return yaml.safe_dump(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": comp.secret, "namespace": comp.namespace},
            "type": "Opaque",
            "stringData": {
                "aws_access_key_id": key_id,
                "aws_secret_access_key": secret,
            },
        },
        sort_keys=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    configure("build-aws-credentials-manifests")

    cluster = args.cluster_name
    target = manifests_secret_name(cluster)
    info("=== Building operator credential manifests ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  target-secret={target}")

    manifests: dict[str, str] = {}
    try:
        for comp in COMPONENTS:
            info(f"Reading {raw_secret_name(cluster, comp.key)}...")
            key_id, secret = _read_credentials(cluster, comp)
            filename = f"cco-secret-{comp.namespace}-{comp.secret}.yaml"
            manifests[filename] = _operator_manifest(comp, key_id, secret)
            info(f"  -> {comp.namespace}/{comp.secret}")
    except (
        subprocess.CalledProcessError,
        binascii.Error,
        KeyError,
        ValueError,
    ) as exc:
        error(f"Failed to read operator credentials: {exc}")
        sys.exit(1)

    outer = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": target, "namespace": cluster},
        "type": "Opaque",
        "stringData": manifests,
    }
    info(f"Applying Secret {target} with {len(manifests)} manifest(s)...")
    try:
        subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=json.dumps(outer),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error(f"Failed to apply Secret {target}: {exc.stderr}")
        sys.exit(1)
    info(f"Secret {target} applied")
