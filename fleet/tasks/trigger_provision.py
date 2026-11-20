"""Trigger the provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-provision --cluster-name NAME --git-repo-url URL --git-revision REV
Creates a PipelineRun for the provision pipeline. The run clones the repository and
revision that pre-provision cloned. Exits 1 on failure.
"""

import argparse
import json
import subprocess
import sys
import textwrap

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--git-repo-url", required=True)
    parser.add_argument("--git-revision", required=True)
    args = parser.parse_args()

    configure("trigger-provision")

    cluster = args.cluster_name
    # A JSON string is a quoted YAML scalar: a commit SHA of digits stays a string.
    repo_url = json.dumps(args.git_repo_url)
    revision = json.dumps(args.git_revision)

    info("=== Triggering provision pipeline ===")
    info(f"  cluster-name={cluster}")
    info(f"  git-repo-url={args.git_repo_url}")
    info(f"  git-revision={args.git_revision}")

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
            - name: git-repo-url
              value: {repo_url}
            - name: git-revision
              value: {revision}
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
