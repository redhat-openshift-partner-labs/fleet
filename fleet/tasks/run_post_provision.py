"""Create a post-provision PipelineRun for a vCluster and wait for completion."""

import argparse
import json
import subprocess
import sys
import textwrap
import time

from fleet.tasks._log import configure, error, info

POLL_INTERVAL = 30


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument(
        "--pipeline-image", default="quay.io/rhopl/fleet-pipeline:latest"
    )
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("run-post-provision")

    info("=== Running post-provision pipeline for vCluster ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  tier={args.tier}")
    info(f"  namespace={args.namespace}")
    info(f"  pipeline-image={args.pipeline_image}")
    info(f"  timeout={args.timeout}s")

    spoke_kubeconfig = f"{cluster}-admin-kubeconfig"

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
              value: {args.tier}
            - name: openshift-cluster
              value: "false"
            - name: spoke-kubeconfig
              value: {spoke_kubeconfig}
            - name: keycloak-url
              value: "https://placeholder"
            - name: keycloak-realm
              value: placeholder
            - name: keycloak-admin-secret
              value: placeholder
            - name: auth-realm
              value: placeholder
            - name: dns-zones
              value: placeholder
            - name: pipeline-image
              value: {args.pipeline_image}
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

    info("Creating post-provision PipelineRun...")
    result = subprocess.run(
        ["oc", "create", "-f", "-"],
        input=pipelinerun_yaml,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to create PipelineRun: {result.stderr}")
        sys.exit(1)

    pr_name = result.stdout.strip().split("/")[-1].split()[0]
    info(f"  -> PipelineRun created: {pr_name}")

    info("Waiting for PipelineRun to complete...")
    deadline = time.time() + args.timeout
    while True:
        result = subprocess.run(
            [
                "oc",
                "get",
                "pipelinerun",
                pr_name,
                "-o",
                "jsonpath={.status.conditions[0]}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            condition = json.loads(result.stdout.strip())
            status = condition.get("status", "")
            reason = condition.get("reason", "")
            info(f"  -> status={status} reason={reason}")

            if status == "True" and reason == "Succeeded":
                info("Post-provision PipelineRun succeeded")
                return

            if status == "False":
                error(f"Post-provision PipelineRun failed: {reason}")
                sys.exit(1)

        if time.time() >= deadline:
            error(f"Timed out waiting for PipelineRun {pr_name} after {args.timeout}s")
            sys.exit(1)

        time.sleep(POLL_INTERVAL)
