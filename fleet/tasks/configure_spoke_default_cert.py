"""Push the leaf certificate to the spoke and set it as the default ingress cert.

CLI: fleet-configure-spoke-default-cert --cluster-name NAME --spoke-kubeconfig PATH
Reads {cluster}-leaf-cert from the hub, applies it to the spoke's openshift-ingress
namespace, then patches the default IngressController. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("configure-spoke-default-cert")

    info("=== Configuring spoke default ingress certificate ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    secret_name = f"{cluster}-leaf-cert"

    info(f"Reading secret '{secret_name}' from hub openshift-ingress...")
    get_result = subprocess.run(
        [
            "oc",
            "get",
            f"secret/{secret_name}",
            "-n",
            "openshift-ingress",
            "-o",
            "jsonpath={.data}",
        ],
        capture_output=True,
        text=True,
    )
    if get_result.returncode != 0:
        error(f"Failed to read hub secret: {get_result.stderr}")
        sys.exit(1)

    data = json.loads(get_result.stdout)
    tls_crt = data["tls.crt"]
    tls_key = data["tls.key"]
    info(f"  -> tls.crt length: {len(tls_crt)} chars")
    info(f"  -> tls.key length: {len(tls_key)} chars")

    secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {secret_name}
          namespace: openshift-ingress
        type: kubernetes.io/tls
        data:
          tls.crt: {tls_crt}
          tls.key: {tls_key}
    """)
    info(f"Applying TLS secret to spoke openshift-ingress...")
    apply_result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {apply_result.returncode}")
    if apply_result.returncode != 0:
        error(f"Failed to apply TLS secret to spoke: {apply_result.stderr}")
        sys.exit(1)
    info("  -> TLS secret applied to spoke")

    patch_json = json.dumps({"spec": {"defaultCertificate": {"name": secret_name}}})
    info("Patching default IngressController on spoke...")
    patch_result = subprocess.run(
        [
            "oc",
            "patch",
            "ingresscontroller",
            "default",
            "-n",
            "openshift-ingress-operator",
            "--type=merge",
            "-p",
            patch_json,
            f"--kubeconfig={args.spoke_kubeconfig}",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc patch exit code: {patch_result.returncode}")
    if patch_result.returncode != 0:
        error(f"Failed to patch IngressController: {patch_result.stderr}")
        sys.exit(1)
    info("Default ingress certificate configured on spoke")
