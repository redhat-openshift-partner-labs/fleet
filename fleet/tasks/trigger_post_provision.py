"""Trigger the post-provision pipeline by creating a PipelineRun.

CLI: fleet-trigger-post-provision --cluster-name NAME --tier TIER
Creates a PipelineRun for the post-provision pipeline. Exits 1 on failure.
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
