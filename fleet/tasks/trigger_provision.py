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
    args = parser.parse_args()

    check_configmap_env()
    cluster = resolve_required(args.cluster_name, "cluster-name", "trigger-provision")

    configure("trigger-provision")

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
