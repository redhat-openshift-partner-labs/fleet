"""Configure OAuth identity providers on the spoke cluster.

CLI: fleet-configure-spoke-oauth --cluster-name NAME --spoke-kubeconfig PATH
     --cluster-dir PATH --keycloak-issuer-url URL --provider-name NAME
Applies htpasswd Secret + OAuth CR to spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._env import resolve_batch
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--spoke-kubeconfig", default=None)
    parser.add_argument("--cluster-dir", default=None)
    parser.add_argument("--keycloak-issuer-url", default=None)
    parser.add_argument("--provider-name", default=None)
    args = parser.parse_args()

    resolve_batch(
        args,
        "configure-spoke-oauth",
        required=[
            "cluster_name",
            "spoke_kubeconfig",
            "cluster_dir",
            "keycloak_issuer_url",
            "provider_name",
        ],
    )

    configure("configure-spoke-oauth")

    info("=== Configuring OAuth identity providers ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")
    info(f"  cluster-dir={args.cluster_dir}")
    info(f"  keycloak-issuer-url={args.keycloak_issuer_url}")
    info(f"  provider-name={args.provider_name}")

    htpasswd_secret_yaml = textwrap.dedent("""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: htpasswd-secret
          namespace: openshift-config
        type: Opaque
        data:
          htpasswd: ""
    """)
    info("Applying htpasswd Secret to openshift-config...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=htpasswd_secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to apply htpasswd secret: {result.stderr}")
        sys.exit(1)
    info("  -> htpasswd Secret applied")

    oauth_yaml = textwrap.dedent(f"""\
        apiVersion: config.openshift.io/v1
        kind: OAuth
        metadata:
          name: cluster
        spec:
          identityProviders:
          - name: htpasswd
            type: HTPasswd
            mappingMethod: claim
            htpasswd:
              fileData:
                name: htpasswd-secret
          - name: {args.provider_name}
            type: OpenID
            mappingMethod: claim
            openID:
              clientID: {args.cluster_name}
              clientSecret:
                name: {args.cluster_name}-keycloak-client
              issuer: {args.keycloak_issuer_url}
              claims:
                preferredUsername:
                - preferred_username
                name:
                - name
                email:
                - email
    """)
    info(
        f"Applying OAuth config with OpenID provider '{args.provider_name}' (issuer: {args.keycloak_issuer_url})..."
    )
    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=oauth_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to apply OAuth config: {result.stderr}")
        sys.exit(1)
    info("OAuth identity providers configured")
