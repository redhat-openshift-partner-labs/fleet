"""Seed hub resources for a test vCluster."""

import argparse
import base64
import subprocess
import sys
import textwrap

from fleet.tasks._env import resolve_batch
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--kubeconfig-file", default=None)
    parser.add_argument("--tier", default=None)
    parser.add_argument("--create-aws-creds", action="store_true", default=False)
    args = parser.parse_args()

    resolve_batch(
        args,
        "seed-test-vcluster",
        required=["cluster_name", "kubeconfig_file", "tier"],
        bool_flags=["create_aws_creds"],
    )
    cluster = args.cluster_name
    configure("seed-test-vcluster")

    info("=== Seeding hub artifacts for test vCluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  kubeconfig-file={args.kubeconfig_file}")
    info(f"  tier={args.tier}")
    info(f"  create-aws-creds={args.create_aws_creds}")

    ns_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {cluster}
    """)
    info(f"Creating namespace '{cluster}'...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=ns_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create namespace: {result.stderr}")
        sys.exit(1)

    try:
        with open(args.kubeconfig_file, encoding="utf-8") as f:
            kubeconfig_data = f.read()
    except FileNotFoundError:
        error(f"Kubeconfig file not found: {args.kubeconfig_file}")
        sys.exit(1)

    encoded = base64.b64encode(kubeconfig_data.encode()).decode()
    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {cluster}-admin-kubeconfig
          namespace: {cluster}
        type: Opaque
        data:
          kubeconfig: {encoded}
    """)
    info(f"Creating kubeconfig secret '{cluster}-admin-kubeconfig'...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create kubeconfig secret: {result.stderr}")
        sys.exit(1)

    mc_yaml = textwrap.dedent(f"""\
        apiVersion: cluster.open-cluster-management.io/v1
        kind: ManagedCluster
        metadata:
          name: {cluster}
          labels:
            tier: {args.tier}
            cloud: vcluster
            vendor: Kubernetes
        spec:
          hubAcceptsClient: true
    """)
    info(f"Creating stub ManagedCluster '{cluster}'...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=mc_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create ManagedCluster: {result.stderr}")
        sys.exit(1)

    indented_kc = textwrap.indent(kubeconfig_data.rstrip(), "    ")
    import_yaml = (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        f"  name: auto-import-secret\n"
        f"  namespace: {cluster}\n"
        "type: Opaque\n"
        "stringData:\n"
        "  kubeconfig: |\n"
        f"{indented_kc}\n"
    )
    info("Creating auto-import-secret...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=import_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create auto-import-secret: {result.stderr}")
        sys.exit(1)

    if args.create_aws_creds:
        creds_yaml = textwrap.dedent(f"""\
            apiVersion: v1
            kind: Secret
            metadata:
              name: aws-credentials
              namespace: {cluster}
            type: Opaque
            stringData:
              aws_access_key_id: placeholder
              aws_secret_access_key: placeholder
        """)
        info("Creating placeholder aws-credentials secret...")
        result = subprocess.run(
            ["oc", "apply", "-f", "-"],
            input=creds_yaml,
            capture_output=True,
            text=True,
        )
        info(f"  -> oc apply exit code: {result.returncode}")
        if result.returncode != 0:
            error(f"Failed to create aws-credentials secret: {result.stderr}")
            sys.exit(1)

    info("Hub artifacts seeded successfully")
