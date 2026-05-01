"""Trigger the post-provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-post-provision --cluster-name NAME --tier TIER
     --base-domain DOMAIN --keycloak-issuer-url URL
     --keycloak-url URL --keycloak-realm REALM
     --keycloak-admin-secret SECRET --auth-realm REALM
Derives dns-zones from the ClusterDeployment baseDomain, then creates a
PipelineRun for the post-provision pipeline. Exits 1 on failure.
"""

import argparse
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--base-domain", required=True)
    parser.add_argument("--keycloak-issuer-url", required=True)
    parser.add_argument("--keycloak-url", required=True)
    parser.add_argument("--keycloak-realm", required=True)
    parser.add_argument("--keycloak-admin-secret", required=True)
    parser.add_argument("--auth-realm", required=True)
    parser.add_argument("--acme-email", required=True)
    args = parser.parse_args()

    configure("trigger-post-provision")

    cluster = args.cluster_name
    tier = args.tier
    base_domain = args.base_domain
    keycloak_issuer_url = args.keycloak_issuer_url
    keycloak_url = args.keycloak_url
    keycloak_realm = args.keycloak_realm
    keycloak_admin_secret = args.keycloak_admin_secret
    auth_realm = args.auth_realm
    acme_email = args.acme_email

    info("=== Triggering post-provision pipeline ===")
    info("Parameters:")
    for key, value in vars(args).items():
        info(f"  {key}={value}")

    info("Reading ClusterDeployment baseDomain...")
    bd_result = subprocess.run(
        [
            "oc",
            "get",
            "clusterdeployment",
            cluster,
            "-n",
            cluster,
            "-o",
            "jsonpath={.spec.baseDomain}",
        ],
        capture_output=True,
        text=True,
    )
    if bd_result.returncode != 0 or not bd_result.stdout.strip():
        error(
            f"Failed to read baseDomain from ClusterDeployment/{cluster}: {bd_result.stderr}"
        )
        sys.exit(1)
    cd_base_domain = bd_result.stdout.strip()
    info(f"  -> baseDomain: {cd_base_domain}")

    dns_zones = f"*.apps.{cluster}.{cd_base_domain},api.{cluster}.{cd_base_domain}"
    info(f"Derived dns-zones: {dns_zones}")

    info("Creating PostSync PipelineRun...")
    pipelinerun_yaml = textwrap.dedent(f"""\
        apiVersion: tekton.dev/v1
        kind: PipelineRun
        metadata:
          generateName: post-provision-{cluster}-
        spec:
          pipelineRef:
            name: post-provision
          params:
            - name: cluster-name
              value: {cluster}
            - name: tier
              value: {tier}
            - name: dns-zones
              value: "{dns_zones}"
            - name: base-domain
              value: {base_domain}
            - name: keycloak-issuer-url
              value: {keycloak_issuer_url}
            - name: keycloak-url
              value: {keycloak_url}
            - name: keycloak-realm
              value: {keycloak_realm}
            - name: keycloak-admin-secret
              value: {keycloak_admin_secret}
            - name: auth-realm
              value: {auth_realm}
            - name: acme-email
              value: {acme_email}
          taskRunTemplate:
            serviceAccountName: fleet-pipeline
            podTemplate:
              securityContext:
                fsGroup: 0
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
    info(f"Creating PipelineRun for cluster {cluster} (tier: {tier})...")
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
    info(f"Post-provision PipelineRun created for cluster {cluster}")
