"""Trigger the post-provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-post-provision --cluster-name NAME --tier TIER
     --base-domain DOMAIN
Derives dns-zones from the ClusterDeployment baseDomain, then creates a
PipelineRun for the post-provision pipeline. Exits 1 on failure.
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
    parser.add_argument("--tier", default=None)
    parser.add_argument("--base-domain", default=None)
    args = parser.parse_args()

    check_configmap_env()
    cluster = resolve_required(
        args.cluster_name, "cluster-name", "trigger-post-provision"
    )
    tier = resolve_required(args.tier, "tier", "trigger-post-provision")
    base_domain = resolve_required(
        args.base_domain, "base-domain", "trigger-post-provision"
    )

    configure("trigger-post-provision")

    info("=== Triggering post-provision pipeline ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  tier={tier}")
    info(f"  base-domain={base_domain}")

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
          taskRunTemplate:
            serviceAccountName: fleet-pipeline
            podTemplate:
              securityContext:
                fsGroup: 0
              imagePullSecrets:
                - name: fleet-pipeline-pull-secret
              envFrom:
                - configMapRef:
                    name: fleet-pipeline-defaults
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
