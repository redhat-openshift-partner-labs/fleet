import argparse
import os
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--values-file", required=False)
    args = parser.parse_args()

    configure("create-test-vcluster")

    info("=== Creating test vCluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={args.cluster_name}")
    info(f"  namespace={args.namespace}")
    info(f"  output-dir={args.output_dir}")

    cmd = [
        "vcluster",
        "create",
        args.cluster_name,
        "-n",
        args.namespace,
        "--connect=false",
    ]
    if args.values_file:
        info(f"  values-file={args.values_file}")
        cmd.extend(["-f", args.values_file])

    info("Creating vCluster...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    info(f"  -> vcluster create exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to create vCluster: {result.stderr}")
        sys.exit(1)

    info("Extracting kubeconfig via vcluster connect --print...")
    result = subprocess.run(
        [
            "vcluster",
            "connect",
            args.cluster_name,
            "-n",
            args.namespace,
            "--print",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> vcluster connect exit code: {result.returncode}")
    if result.returncode != 0:
        error(f"Failed to get kubeconfig: {result.stderr}")
        sys.exit(1)

    kubeconfig_path = os.path.join(args.output_dir, "kubeconfig")
    with open(kubeconfig_path, "w") as fh:
        fh.write(result.stdout)
    info(f"Kubeconfig written to {kubeconfig_path}")
