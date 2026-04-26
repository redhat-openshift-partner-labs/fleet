"""Configure OAuth identity providers on the spoke cluster.

CLI: fleet-configure-spoke-oauth --cluster-name NAME --spoke-kubeconfig PATH --cluster-dir PATH
Applies htpasswd Secret + OAuth CR to spoke. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--cluster-dir", required=True)
    args = parser.parse_args()

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
        print(f"Failed to apply htpasswd secret: {result.stderr}", file=sys.stderr)
        sys.exit(1)

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
          - name: oidc
            type: OpenID
            mappingMethod: claim
            openID:
              clientID: {args.cluster_name}
              clientSecret:
                name: openid-client-secret-{args.cluster_name}
              issuer: https://keycloak.example.com/realms/openshift
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
        print(f"Failed to apply OAuth config: {result.stderr}", file=sys.stderr)
        sys.exit(1)
