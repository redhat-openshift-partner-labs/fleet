"""Trigger the provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-provision --cluster-name NAME
Creates a PipelineRun for the provision pipeline. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._env import check_configmap_env, resolve_required
from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", default=None)
    parser.add_argument("--base-domain", default=None)
    parser.add_argument("--keycloak-issuer-url", default=None)
    parser.add_argument("--keycloak-url", default=None)
    parser.add_argument("--keycloak-realm", default=None)
    parser.add_argument("--keycloak-admin-secret", default=None)
    parser.add_argument("--auth-realm", default=None)
    parser.add_argument("--acme-email", default=None)
    args = parser.parse_args()

    check_configmap_env()
    args.cluster_name = resolve_required(
        args.cluster_name, "cluster-name", "trigger-provision"
    )
    args.base_domain = resolve_required(
        args.base_domain, "base-domain", "trigger-provision"
    )
    args.keycloak_issuer_url = resolve_required(
        args.keycloak_issuer_url, "keycloak-issuer-url", "trigger-provision"
    )
    args.keycloak_url = resolve_required(
        args.keycloak_url, "keycloak-url", "trigger-provision"
    )
    args.keycloak_realm = resolve_required(
        args.keycloak_realm, "keycloak-realm", "trigger-provision"
    )
    args.keycloak_admin_secret = resolve_required(
        args.keycloak_admin_secret, "keycloak-admin-secret", "trigger-provision"
    )
    args.auth_realm = resolve_required(
        args.auth_realm, "auth-realm", "trigger-provision"
    )
    args.acme_email = resolve_required(
        args.acme_email, "acme-email", "trigger-provision"
    )

    configure("trigger-provision")

    cluster = args.cluster_name

    info("=== Triggering provision pipeline ===")
    info(f"  cluster-name={cluster}")

    pipelinerun_yaml = textwrap.dedent(f"""\
        apiVersion: tekton.dev/v1
        kind: PipelineRun
        metadata:
          generateName: provision-{cluster}-
        spec:
          pipelineRef:
            name: provision
          params:
            - name: cluster-name
              value: {cluster}
            - name: base-domain
              value: {args.base_domain}
            - name: keycloak-issuer-url
              value: {args.keycloak_issuer_url}
            - name: keycloak-url
              value: {args.keycloak_url}
            - name: keycloak-realm
              value: {args.keycloak_realm}
            - name: keycloak-admin-secret
              value: {args.keycloak_admin_secret}
            - name: auth-realm
              value: {args.auth_realm}
            - name: acme-email
              value: {args.acme_email}
          taskRunTemplate:
            serviceAccountName: fleet-pipeline
            podTemplate:
              securityContext:
                fsGroup: 0
              imagePullSecrets:
                - name: fleet-pipeline-pull-secret
          workspaces:
            - name: shared-workspace
              volumeClaimTemplate:
                spec:
                  accessModes:
                    - ReadWriteOnce
                  resources:
                    requests:
                      storage: 1Gi
                  storageClassName: gp3-csi
    """)
    info(f"Creating PipelineRun for cluster {cluster}...")
    result = subprocess.run(
        ["oc", "create", "-f", "-"],
        input=pipelinerun_yaml,
        capture_output=True,
        text=True,
    )
    info(f"  -> oc create exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create PipelineRun: {result.stderr}")
        sys.exit(1)
    info(f"Provision PipelineRun created for cluster {cluster}")
