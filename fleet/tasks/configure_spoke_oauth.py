"""Configure OAuth identity providers on the spoke cluster.

CLI: fleet-configure-spoke-oauth --cluster-name NAME --spoke-kubeconfig PATH
     --keycloak-issuer-url URL --provider-name NAME
Reads the keycloak-client secret from the hub, pushes it to the spoke, then
applies htpasswd Secret + OAuth CR to spoke. Exits 1 on failure.
"""

import argparse
import base64
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def _read_hub_secret_key(namespace: str, secret_name: str, key: str) -> str:
    jsonpath = f"jsonpath={{.data.{key}}}"
    result = subprocess.run(
        ["oc", "get", "secret", secret_name, "-n", namespace, "-o", jsonpath],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read {key} from hub secret {secret_name}: {result.stderr}")
        sys.exit(1)
    return base64.b64decode(result.stdout.strip()).decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--keycloak-issuer-url", required=True)
    parser.add_argument("--provider-name", default="RedHat")
    args = parser.parse_args()

    configure("configure-spoke-oauth")

    info("=== Configuring OAuth identity providers ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")
    info(f"  keycloak-issuer-url={args.keycloak_issuer_url}")
    info(f"  provider-name={args.provider_name}")

    hub_secret = f"{args.cluster_name}-keycloak-client"
    info(f"Reading keycloak client credentials from hub secret '{hub_secret}'...")
    client_id = _read_hub_secret_key("openshift-pipelines", hub_secret, "client-id")
    client_secret = _read_hub_secret_key(
        "openshift-pipelines", hub_secret, "client-secret"
    )
    info("  -> Hub secret read OK")

    info(f"Reading admin password from ClusterDeployment '{args.cluster_name}'...")
    pwd_secret_result = subprocess.run(
        [
            "oc",
            "get",
            "clusterdeployment",
            args.cluster_name,
            "-n",
            args.cluster_name,
            "-o",
            "jsonpath={.spec.clusterMetadata.adminPasswordSecretRef.name}",
        ],
        capture_output=True,
        text=True,
    )
    if pwd_secret_result.returncode != 0:
        error(f"Failed to read admin password secret ref: {pwd_secret_result.stderr}")
        sys.exit(1)
    admin_pwd_secret = pwd_secret_result.stdout.strip()
    info(f"  -> admin password secret: {admin_pwd_secret}")
    admin_password = _read_hub_secret_key(
        args.cluster_name, admin_pwd_secret, "password"
    )
    info("  -> admin password read OK")

    htpasswd_result = subprocess.run(
        ["htpasswd", "-Bbn", "kubeadmin", admin_password],
        capture_output=True,
        text=True,
    )
    if htpasswd_result.returncode != 0:
        error(f"Failed to generate htpasswd entry: {htpasswd_result.stderr}")
        sys.exit(1)
    htpasswd_entry = htpasswd_result.stdout.strip()
    info("  -> htpasswd entry generated")

    htpasswd_secret_yaml = (
        "apiVersion: v1\n"
        "kind: Secret\n"
        "metadata:\n"
        "  name: htpasswd-secret\n"
        "  namespace: openshift-config\n"
        "type: Opaque\n"
        "stringData:\n"
        f"  htpasswd: {htpasswd_entry}\n"
    )
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

    keycloak_secret_yaml = textwrap.dedent(f"""\
        apiVersion: v1
        kind: Secret
        metadata:
          name: {args.cluster_name}-keycloak-client
          namespace: openshift-config
        type: Opaque
        stringData:
          clientSecret: {client_secret}
    """)
    info(f"Pushing keycloak-client secret to spoke openshift-config...")
    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={args.spoke_kubeconfig}"],
        input=keycloak_secret_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc apply exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to apply keycloak-client secret to spoke: {result.stderr}")
        sys.exit(1)
    info("  -> keycloak-client Secret applied to spoke")

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
              clientID: {client_id}
              clientSecret:
                name: {args.cluster_name}-keycloak-client
              issuer: {args.keycloak_issuer_url}
              claims:
                preferredUsername:
                - email
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
