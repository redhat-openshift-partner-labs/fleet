"""Extract the spoke admin kubeconfig from Hive into the pipeline workspace.

CLI: fleet-extract-kubeconfig --cluster-name NAME --output-dir DIR
Reads adminKubeconfigSecretRef from ClusterDeployment, extracts the kubeconfig key to output-dir.
Exits 1 if extraction fails.
"""

import argparse
import subprocess
import sys

from fleet.tasks._log import configure, error, info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=False)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("extract-kubeconfig")

    info("=== Extracting spoke kubeconfig ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  output-dir={args.output_dir}")

    if not args.spoke_kubeconfig:
        info(f"Getting ClusterDeployment admin kubeconfig secret ref...")
        result = subprocess.run(
            [
                "oc",
                "get",
                "clusterdeployment",
                cluster,
                "-n",
                cluster,
                "-o",
                "jsonpath={.spec.clusterMetadata.adminKubeconfigSecretRef.name}",
            ],
            capture_output=True,
            text=True,
        )
        secret_name = (
            result.stdout.strip()
            if result.returncode == 0 and result.stdout.strip()
            else f"{cluster}-admin-kubeconfig"
        )
    else:
        secret_name = args.spoke_kubeconfig

    info(f"  -> Secret name: {secret_name}")

    info(
        f"Extracting kubeconfig from secret '{secret_name}' in ns '{cluster}' to '{args.output_dir}'..."
    )
    extract = subprocess.run(
        [
            "oc",
            "extract",
            f"secret/{secret_name}",
            "-n",
            cluster,
            f"--to={args.output_dir}",
            "--keys=kubeconfig",
            "--confirm",
        ],
        capture_output=True,
        text=True,
    )
    info(f"  -> oc extract exit code: {extract.returncode}")
    if extract.returncode != 0:
        error(f"Failed to extract kubeconfig: {extract.stderr}")
        sys.exit(1)
    info(f"Kubeconfig extracted to {args.output_dir}")
