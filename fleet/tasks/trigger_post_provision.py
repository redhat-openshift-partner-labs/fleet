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
    args = parser.parse_args()

    cluster = args.cluster_name
    tier = args.tier
    base_domain = args.base_domain
    keycloak_issuer_url = args.keycloak_issuer_url
    keycloak_url = args.keycloak_url
    keycloak_realm = args.keycloak_realm
    keycloak_admin_secret = args.keycloak_admin_secret
    auth_realm = args.auth_realm

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
        print(
            f"Failed to read baseDomain: {bd_result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    cd_base_domain = bd_result.stdout.strip()
    dns_zones = f"*.apps.{cluster}.{cd_base_domain},api.{cluster}.{cd_base_domain}"

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

    result = subprocess.run(
        ["oc", "create", "-f", "-"],
        input=pipelinerun_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to create PipelineRun: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Post-provision PipelineRun created for {cluster}")
