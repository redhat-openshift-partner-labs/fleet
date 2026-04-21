import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout", default="60m")
    args = parser.parse_args()

    cluster = args.cluster_name

    print(
        f"Waiting for ClusterDeployment {cluster} to be provisioned (timeout: {args.timeout})..."
    )
    result = subprocess.run(
        [
            "oc",
            "wait",
            "--for=condition=Provisioned",
            f"clusterdeployment/{cluster}",
            "-n",
            cluster,
            f"--timeout={args.timeout}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"ClusterDeployment {cluster} not provisioned: {result.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Cluster {cluster} provisioned successfully")
