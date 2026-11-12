"""Build the Hive install-manifests Secret carrying per-operator AWS credentials (scoped clusters).

CLI: fleet-build-aws-credentials-manifests --cluster-name NAME
Discovers the operators from the cluster's annotated AccessKeys (discover_components), reads
each one's raw credential Secret (Crossplane AccessKey: username/password) and writes Secret
<cluster>-cloud-credentials-manifests in namespace {cluster}. Each key is a Secret manifest for
the operator's target namespace/name, which Hive adds to the install manifests via
ClusterDeployment.spec.provisioning.manifestsSecretRef (credentialsMode Manual). A credential
annotated delivery=post-provision is skipped: its target namespace does not exist at install
time and a post-provision task delivers it. Secret values go through stdin only and are never
logged. Exits 1 on any failure, including an overlay whose AccessKeys carry no target
annotations.
"""

import argparse
import binascii
import json
import subprocess
import sys

import yaml

from fleet.tasks._aws_components import (
    DiscoveryError,
    OperatorCredential,
    discover_components,
    install_credentials,
    manifests_secret_name,
    read_raw_credentials,
)
from fleet.tasks._log import configure, error, info


def _operator_manifest(comp: OperatorCredential, key_id: str, secret: str) -> str:
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
        discovered = discover_components(cluster)
        components = install_credentials(discovered)
        for comp in discovered:
            if comp not in components:
                info(
                    f"Skipping {comp.raw_secret} ({comp.credentials_request}): "
                    "delivered post-provision"
                )
        for comp in components:
            info(f"Reading {comp.raw_secret} ({comp.credentials_request})...")
            key_id, secret = read_raw_credentials(cluster, comp)
            filename = f"cco-secret-{comp.namespace}-{comp.secret}.yaml"
            manifests[filename] = _operator_manifest(comp, key_id, secret)
            info(f"  -> {comp.namespace}/{comp.secret}")
    except (
        DiscoveryError,
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
