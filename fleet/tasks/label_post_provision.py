import argparse
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name

    result = subprocess.run(
        [
            "oc",
            "label",
            f"managedcluster/{cluster}",
            "provisioned=true",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to label ManagedCluster: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"ManagedCluster {cluster} labeled provisioned=true")
