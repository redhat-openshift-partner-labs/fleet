"""Configure OAuth identity providers on the spoke cluster.

CLI: fleet-configure-spoke-oauth --cluster-name NAME --spoke-kubeconfig PATH
     --cluster-dir PATH --keycloak-issuer-url URL --provider-name NAME
Applies htpasswd Secret + OAuth CR to spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--cluster-dir", required=True)
    parser.add_argument("--keycloak-issuer-url", required=True)
    parser.add_argument("--provider-name", default="RedHat")
    args = parser.parse_args()

    configure("configure-spoke-oauth")

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

    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=htpasswd_secret_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to apply htpasswd secret: {result.stderr}")
        sys.exit(1)
    info("Configured htpasswd Secret")

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

    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=oauth_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to apply OAuth config: {result.stderr}")
        sys.exit(1)
    info("Configured OAuth identity providers")
