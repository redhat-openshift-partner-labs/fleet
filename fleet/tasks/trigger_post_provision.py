"""Trigger the post-provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-post-provision --cluster-name NAME --tier TIER
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
    args = parser.parse_args()

    cluster = args.cluster_name
    tier = args.tier

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

    base_domain = bd_result.stdout.strip()
    dns_zones = f"*.apps.{cluster}.{base_domain},api.{cluster}.{base_domain}"

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
