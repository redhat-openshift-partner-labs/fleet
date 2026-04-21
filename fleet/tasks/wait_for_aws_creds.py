import argparse
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    cluster = args.cluster_name
    timeout = args.timeout_seconds
    elapsed = 0
    interval = 10

    print(f"Waiting for aws-credentials Secret in namespace {cluster}...")

    while elapsed < timeout:
        result = subprocess.run(
            ["oc", "get", "secret", "aws-credentials", "-n", cluster],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"aws-credentials Secret found in {cluster}")
            return

        time.sleep(interval)
        elapsed += interval
        print(f"  waiting... ({elapsed}s / {timeout}s)")

    print(
        f"ERROR: Timed out after {timeout}s waiting for aws-credentials",
        file=sys.stderr,
    )
    subprocess.run(
        ["oc", "get", "user.iam,accesskey.iam,job", "-n", cluster],
        capture_output=True,
        text=True,
    )
    sys.exit(1)
