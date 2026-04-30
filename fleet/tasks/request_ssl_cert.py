"""Request an SSL certificate from the hub cert-manager ClusterIssuer.

CLI: fleet-request-ssl-cert --cluster-name NAME --dns-zones ZONE1,ZONE2
Creates a Certificate CR referencing hub-ca ClusterIssuer. Exits 1 on failure.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--dns-zones", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    zones = [z.strip() for z in args.dns_zones.split(",")]

    configure("request-ssl-cert")

    info("=== Requesting SSL certificate ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  dns-zones={zones}")

    dns_names = "\n".join(f'    - "{z}"' for z in zones)
    cert_yaml = (
        f"apiVersion: cert-manager.io/v1\n"
        f"kind: Certificate\n"
        f"metadata:\n"
        f"  name: {cluster}-wildcard-certificate\n"
        f"  namespace: openshift-ingress\n"
        f"spec:\n"
        f"  secretName: {cluster}-wildcard-certificate\n"
        f"  issuerRef:\n"
        f"    name: letsencrypt-{cluster}\n"
        f"    kind: ClusterIssuer\n"
        f"  dnsNames:\n"
        f"{dns_names}\n"
    )
    info(
        f"Creating Certificate CR '{cluster}-wildcard-certificate' with DNS: {dns_names}"
    )
    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=cert_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create certificate: {result.stderr}")
        sys.exit(1)
    info(f"Certificate request '{cluster}-wildcard-certificate' created")
