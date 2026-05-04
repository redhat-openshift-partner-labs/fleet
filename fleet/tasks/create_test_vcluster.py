"""Create a vCluster and extract its kubeconfig."""

import argparse
import base64
import os
import subprocess
import sys
import textwrap
import time

from fleet.tasks._log import configure, error, info


def _generate_values(
    cluster_name: str,
    namespace: str,
    extra_sans: list[str] | None = None,
    route_san: str | None = None,
) -> str:
    sans = [f"{cluster_name}.{namespace}.svc.cluster.local"]
    if extra_sans:
        sans.extend(extra_sans)
    sans_yaml = "\n".join(f"              - {s}" for s in sans)
    result = textwrap.dedent(f"""\
        controlPlane:
          proxy:
            extraSANs:
{sans_yaml}
        experimental:
          deploy:
            host:
              manifests: |-
                apiVersion: rbac.authorization.k8s.io/v1
                kind: RoleBinding
                metadata:
                  name: vc-{cluster_name}-cluster-admin
                  namespace: {namespace}
                roleRef:
                  apiGroup: rbac.authorization.k8s.io
                  kind: ClusterRole
                  name: cluster-admin
                subjects:
                  - kind: ServiceAccount
                    name: vc-{cluster_name}
                    namespace: {namespace}
                ---
                apiVersion: rbac.authorization.k8s.io/v1
                kind: RoleBinding
                metadata:
                  name: vc-workload-{cluster_name}-cluster-admin
                  namespace: {namespace}
                roleRef:
                  apiGroup: rbac.authorization.k8s.io
                  kind: ClusterRole
                  name: cluster-admin
                subjects:
                  - kind: ServiceAccount
                    name: vc-workload-{cluster_name}
                    namespace: {namespace}
    """)
    if route_san:
        result += textwrap.dedent(f"""\
            exportKubeConfig:
              server: https://{route_san}:443
        """)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--values-file", required=False)
    parser.add_argument("--extra-sans", nargs="*", default=[])
    parser.add_argument("--route-san", required=False, default=None)
    args = parser.parse_args()

    configure("create-test-vcluster")

    info("=== Creating test vCluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  namespace={args.namespace}")
    info(f"  output-dir={args.output_dir}")

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        info(f"  output-dir created: {args.output_dir}")

    cmd = [
        "vcluster",
        "create",
        args.cluster_name,
        "-n",
        args.namespace,
        "--connect=false",
    ]

    if args.values_file:
        info(f"  values-file={args.values_file}")
        cmd.extend(["-f", args.values_file])
    else:
        extra_sans = list(args.extra_sans)
        if args.route_san and args.route_san not in extra_sans:
            extra_sans.append(args.route_san)
        values_content = _generate_values(
            args.cluster_name,
            args.namespace,
            extra_sans=extra_sans,
            route_san=args.route_san,
        )
        values_path = os.path.join(args.output_dir, "vcluster-values.yaml")
        with open(values_path, "w", encoding="utf-8") as fh:
            fh.write(values_content)
        info(f"  generated values file: {values_path}")
        cmd.extend(["-f", values_path])

    info("Creating vCluster...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    info(f"  -> vcluster create exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create vCluster: {result.stderr}")
        sys.exit(1)

    info("vCluster created, wait 30s for kubeconfig secret to be created...")
    time.sleep(30)

    secret_name = f"vc-{args.cluster_name}"
    info(f"Extracting kubeconfig from secret {secret_name}...")
    result = subprocess.run(
        [
            "oc",
            "get",
            "secret",
            secret_name,
            "-n",
            args.namespace,
            "-o",
            "jsonpath={.data.config}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc get secret exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to get kubeconfig: {result.stderr}")
        sys.exit(1)

    kubeconfig_data = base64.b64decode(result.stdout).decode("utf-8")

    kubeconfig_path = os.path.join(args.output_dir, "kubeconfig")
    with open(kubeconfig_path, "w", encoding="utf-8") as fh:
        fh.write(kubeconfig_data)
    info(f"Kubeconfig written to {kubeconfig_path}")

    if args.route_san:
        info(f"Creating passthrough route with hostname {args.route_san}...")
        result = subprocess.run(
            [
                "oc",
                "create",
                "route",
                "passthrough",
                args.cluster_name,
                f"--service={args.cluster_name}",
                f"--hostname={args.route_san}",
                "-n",
                args.namespace,
            ],
            capture_output=True,
            text=True,
        )
        info(f"  -> oc create route passthrough exit code: {result.returncode}")
        if result.returncode != 0:
            error(f"Failed to create passthrough route: {result.stderr}")
            sys.exit(1)
