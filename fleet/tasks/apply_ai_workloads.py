"""Apply AI tier workloads to the spoke cluster.

CLI: fleet-apply-ai-workloads --cluster-name NAME --source-dir DIR --spoke-kubeconfig PATH
Implements sequential operator installation with readiness checks for AI tier:
1. NFD Subscription -> CSV Ready
2. NFD Operand -> NodeFeatureDiscovery Available
3. GPU Operator Subscription -> CSV Ready
4. OpenShift AI Subscription -> CSV Ready
5. DataScienceCluster -> Ready condition
Exits 1 on failure.
"""

import argparse
import json
import sys
import time

from fleet._retry import run_with_retry
from fleet.tasks._log import configure, error, info


def wait_for_csv(namespace: str, csv_name_pattern: str, kubeconfig: str, timeout: int = 600) -> bool:
    """Wait for ClusterServiceVersion to reach Succeeded phase."""
    info(f"Waiting for CSV matching '{csv_name_pattern}' in namespace {namespace} (timeout: {timeout}s)")

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Get CSVs in the namespace
        result = run_with_retry([
            "oc", "get", "csv",
            "-n", namespace,
            "-o", "json",
            f"--kubeconfig={kubeconfig}"
        ], capture_output=True, text=True)

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

                    # Get detailed failure information
                    info("=== CSV Failure Details ===")
                    csv_detail_result = run_with_retry([
                        "oc", "get", "csv", csv_name,
                        "-n", namespace,
                        "-o", "yaml",
                        f"--kubeconfig={kubeconfig}"
                    ], capture_output=True, text=True)

                    if csv_detail_result.returncode == 0:
                        # Extract status conditions from YAML
                        import re
                        conditions_match = re.search(r'conditions:(.*?)(?=\n\w|\nstatus:|\Z)', csv_detail_result.stdout, re.DOTALL)
                        if conditions_match:
                            info(f"CSV conditions: {conditions_match.group(1).strip()}")

                    # Get InstallPlan details
                    info("=== InstallPlan Status ===")
                    install_plan_result = run_with_retry([
                        "oc", "get", "csv", csv_name,
                        "-n", namespace,
                        "-o", "jsonpath={.status.installPlanRef.name}",
                        f"--kubeconfig={kubeconfig}"
                    ], capture_output=True, text=True)

                    if install_plan_result.returncode == 0 and install_plan_result.stdout.strip():
                        install_plan_name = install_plan_result.stdout.strip()
                        info(f"InstallPlan: {install_plan_name}")

                        plan_detail_result = run_with_retry([
                            "oc", "get", "installplan", install_plan_name,
                            "-n", namespace,
                            "-o", "yaml",
                            f"--kubeconfig={kubeconfig}"
                        ], capture_output=True, text=True)

                        if plan_detail_result.returncode == 0:
                            # Extract status conditions from InstallPlan YAML
                            conditions_match = re.search(r'conditions:(.*?)(?=\n\w|\nstatus:|\Z)', plan_detail_result.stdout, re.DOTALL)
                            if conditions_match:
                                info(f"InstallPlan conditions: {conditions_match.group(1).strip()}")

                    return False
            else:
                info(f"  -> CSV matching '{csv_name_pattern}' not found yet")

        except json.JSONDecodeError as e:
            error(f"Failed to parse CSV JSON: {e}")

        time.sleep(10)

    error(f"Timeout waiting for CSV matching '{csv_name_pattern}' in {namespace}")
    return False


def wait_for_nfd_ready(kubeconfig: str, timeout: int = 300) -> bool:
    """Wait for NodeFeatureDiscovery instance to be Available."""
    start_time = time.time()
    info("Waiting for NodeFeatureDiscovery instance to be Available...")

    while time.time() - start_time < timeout:
        result = run_with_retry([
            "oc", "get", "nodefeaturesdiscovery", "nfd-instance",
            "-n", "openshift-nfd",
            "-o", "jsonpath={.status.conditions[?(@.type=='Available')].status}",
            f"--kubeconfig={kubeconfig}"
        ], capture_output=True, text=True)

        if result.returncode == 0 and result.stdout.strip() == "True":
            info("  -> NodeFeatureDiscovery is Available")
            return True

        if result.returncode != 0:
            info("  -> NodeFeatureDiscovery not found yet, waiting...")
        else:
            info(f"  -> NodeFeatureDiscovery Available condition: {result.stdout.strip()}")

        time.sleep(10)

    error("Timeout waiting for NodeFeatureDiscovery to be Available")
    return False


def wait_for_datasciencecluster_ready(kubeconfig: str, timeout: int = 900) -> bool:
    """Wait for DataScienceCluster to be Ready."""
    start_time = time.time()
    info("Waiting for DataScienceCluster to be Ready...")

    while time.time() - start_time < timeout:
        result = run_with_retry([
            "oc", "get", "datasciencecluster", "default-dsc",
            "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
            f"--kubeconfig={kubeconfig}"
        ], capture_output=True, text=True)

        if result.returncode == 0 and result.stdout.strip() == "True":
            info("  -> DataScienceCluster is Ready")
            return True

        if result.returncode != 0:
            info("  -> DataScienceCluster not found yet, waiting...")
        else:
            info(f"  -> DataScienceCluster Ready condition: {result.stdout.strip()}")

        time.sleep(15)

    error("Timeout waiting for DataScienceCluster to be Ready")
    return False


def apply_manifests_and_wait(source_dir: str, kubeconfig: str) -> bool:
    """Apply AI tier manifests and wait for readiness."""
    info("Building and applying AI tier manifests...")

    # Build kustomize manifests
    build = run_with_retry(
        ["kustomize", "build", source_dir],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        error(f"kustomize build failed: {build.stderr}")
        return False

    # Apply manifests
    apply = run_with_retry(
        ["oc", "apply", "-f", "-", f"--kubeconfig={kubeconfig}"],
        input=build.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        error(f"oc apply failed: {apply.stderr}")
        return False

    info(f"Applied AI tier manifests: {apply.stdout.strip()}")

    # Phase 1: Wait for NFD CSV
    if not wait_for_csv("openshift-nfd", "nfd", kubeconfig, 600):
        return False

    # Phase 2: Wait for NFD operand
    if not wait_for_nfd_ready(kubeconfig, 300):
        return False

    # Phase 3: Wait for GPU Operator CSV
    if not wait_for_csv("nvidia-gpu-operator", "gpu-operator-certified", kubeconfig, 900):
        return False

    # Phase 4: Wait for OpenShift AI CSV
    if not wait_for_csv("redhat-ods-operator", "rhods-operator", kubeconfig, 900):
        return False

    # Phase 5: Wait for Serverless Operator CSV (provides kserve)
    if not wait_for_csv("openshift-serverless", "serverless-operator", kubeconfig, 900):
        return False

    # Phase 6: Wait for DataScienceCluster (creates its own DSCInitialization internally)
    if not wait_for_datasciencecluster_ready(kubeconfig, 900):
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    args = parser.parse_args()

    cluster = args.cluster_name
    configure("apply-ai-workloads")

    info("=== Applying AI tier workloads to spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={args.source_dir}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")

    success = apply_manifests_and_wait(args.source_dir, args.spoke_kubeconfig)

    if success:
        info("AI tier workloads applied successfully")
    else:
        error("Failed to apply AI tier workloads")
        sys.exit(1)