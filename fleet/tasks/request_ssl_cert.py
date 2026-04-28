"""Request an SSL certificate from the hub cert-manager ClusterIssuer.

CLI: fleet-request-ssl-cert --cluster-name NAME --dns-zones ZONE1,ZONE2
Creates a Certificate CR referencing hub-ca ClusterIssuer. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--dns-zones", required=True)
    args = parser.parse_args()

    configure("request-ssl-cert")

    cluster = args.cluster_name
    zones = [z.strip() for z in args.dns_zones.split(",")]

    dns_names = "\n".join(f"    - {z}" for z in zones)
    cert_yaml = textwrap.dedent(f"""\
        apiVersion: cert-manager.io/v1
        kind: Certificate
        metadata:
          name: {cluster}-tls
        spec:
          secretName: {cluster}-tls
          issuerRef:
            name: hub-ca
            kind: ClusterIssuer
          dnsNames:
        {dns_names}
    """)

    result = subprocess.run(
        ["oc", "apply", "-f", "-"],
        input=cert_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to create certificate: {result.stderr}")
        sys.exit(1)

    info(f"Requested TLS certificate for {cluster}")
