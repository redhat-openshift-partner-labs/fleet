"""Apply virtualization workloads to the spoke cluster with operator sequencing.

CLI: fleet-apply-virt-workloads --cluster-name NAME --source-dir DIR --spoke-kubeconfig PATH
Applies NFD and CNV operators in sequence, waiting for each to be ready before proceeding.
Exits 1 on failure.
"""

import argparse
import json
import sys
import time

from fleet._retry import run_with_retry
from fleet.tasks._log import configure, error, info


def apply_manifest(manifest_path: str, spoke_kubeconfig: str) -> bool:
    """Apply a single manifest file to the spoke cluster."""
    info(f"Applying manifest: {manifest_path}")

    apply = run_with_retry(
        ["oc", "apply", "-f", manifest_path, f"--kubeconfig={spoke_kubeconfig}"],
        capture_output=True,
        text=True,
    )

    if apply.returncode != 0:
        error(f"Failed to apply {manifest_path}: {apply.stderr}")
        return False

    info(f"  -> Applied: {apply.stdout.strip()}")
    return True


def wait_for_csv(
    namespace: str, csv_name_pattern: str, spoke_kubeconfig: str, timeout: int = 600
) -> bool:
    """Wait for ClusterServiceVersion to reach Succeeded phase."""
    info(
        f"Waiting for CSV matching '{csv_name_pattern}' in namespace {namespace} (timeout: {timeout}s)"
    )

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Get CSVs in the namespace
        result = run_with_retry(
            [
                "oc",
                "get",
                "csv",
                "-n",
                namespace,
                "-o",
                "json",
                f"--kubeconfig={spoke_kubeconfig}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error(f"Failed to get CSVs: {result.stderr}")
            time.sleep(10)
            continue

        try:
            csvs_data = json.loads(result.stdout)

            # Find matching CSV
            matching_csv = None
            for csv in csvs_data.get("items", []):
                csv_name = csv["metadata"]["name"]
                if csv_name_pattern in csv_name:
                    matching_csv = csv
                    break

            if matching_csv:
                phase = matching_csv.get("status", {}).get("phase", "")
                csv_name = matching_csv["metadata"]["name"]

                info(f"  -> CSV {csv_name} phase: {phase}")

                if phase == "Succeeded":
                    info(f"  -> CSV {csv_name} is ready")
                    return True
                if phase == "Failed":
                    error(f"CSV {csv_name} failed to install")
                    return False
            else:
                info(f"  -> CSV matching '{csv_name_pattern}' not found yet")

        except json.JSONDecodeError as e:
            error(f"Failed to parse CSV JSON: {e}")

        time.sleep(10)

    error(f"Timeout waiting for CSV matching '{csv_name_pattern}' in {namespace}")
    return False


def wait_for_condition(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    resource_type: str,
    resource_name: str,
    namespace: str,
    condition: str,
    spoke_kubeconfig: str,
    timeout: int = 300,
) -> bool:
    """Wait for a custom resource to have a specific condition."""
    info(
        f"Waiting for {resource_type}/{resource_name} condition '{condition}' in {namespace} (timeout: {timeout}s)"
    )

    start_time = time.time()
    while time.time() - start_time < timeout:
        result = run_with_retry(
            [
                "oc",
                "get",
                resource_type,
                resource_name,
                "-n",
                namespace,
                "-o",
                "json",
                f"--kubeconfig={spoke_kubeconfig}",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            info(f"  -> {resource_type}/{resource_name} not found yet, waiting...")
            time.sleep(10)
            continue

        try:
            resource_data = json.loads(result.stdout)
            conditions = resource_data.get("status", {}).get("conditions", [])

            for cond in conditions:
                if cond.get("type") == condition:
                    status = cond.get("status", "")
                    info(f"  -> Condition '{condition}' status: {status}")

                    if status == "True":
                        info(
                            f"  -> {resource_type}/{resource_name} condition '{condition}' is ready"
                        )
                        return True
                    if status == "False":
                        reason = cond.get("reason", "Unknown")
                        message = cond.get("message", "")
                        error(f"Condition '{condition}' failed: {reason} - {message}")

            info(f"  -> Condition '{condition}' not ready yet")

        except json.JSONDecodeError as e:
            error(f"Failed to parse resource JSON: {e}")

        time.sleep(10)

    error(
        f"Timeout waiting for {resource_type}/{resource_name} condition '{condition}'"
    )
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("apply-virt-workloads")

    info("=== Applying virtualization workloads to spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={args.source_dir}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    source_dir = args.source_dir
    kubeconfig = args.spoke_kubeconfig

    # Phase 1: Apply NFD subscription and wait for operator
    info("Phase 1: Installing Node Feature Discovery operator")

    if not apply_manifest(f"{source_dir}/nfd-subscription.yaml", kubeconfig):
        sys.exit(1)

    if not wait_for_csv("openshift-nfd", "nfd", kubeconfig, timeout=600):
        sys.exit(1)

    # Phase 2: Apply NFD operand and wait for readiness
    info("Phase 2: Creating NFD operand")

    if not apply_manifest(f"{source_dir}/nfd-operand.yaml", kubeconfig):
        sys.exit(1)

    if not wait_for_condition(
        "NodeFeatureDiscovery", "nfd-instance", "openshift-nfd", "Available", kubeconfig
    ):
        sys.exit(1)

    # Phase 3: Apply CNV subscription and wait for operator
    info("Phase 3: Installing OpenShift Virtualization operator")

    if not apply_manifest(f"{source_dir}/cnv-subscription.yaml", kubeconfig):
        sys.exit(1)

    if not wait_for_csv(
        "openshift-cnv", "kubevirt-hyperconverged", kubeconfig, timeout=900
    ):
        sys.exit(1)

    # Phase 4: Apply HyperConverged CR and wait for readiness
    info("Phase 4: Creating HyperConverged operand")

    if not apply_manifest(f"{source_dir}/hyperconverged.yaml", kubeconfig):
        sys.exit(1)

    if not wait_for_condition(
        "HyperConverged",
        "kubevirt-hyperconverged",
        "openshift-cnv",
        "Available",
        kubeconfig,
    ):
        sys.exit(1)

    info("Virtualization workloads successfully applied and ready")
