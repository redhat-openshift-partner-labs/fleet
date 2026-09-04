"""Apply AI workloads to the spoke cluster with version-aware operator sequencing.

CLI: fleet-apply-ai-workloads --cluster-name NAME --source-dir DIR
       --spoke-kubeconfig PATH --openshift-ai-version v2|v3
Applies common operators (NFD, GPU, Serverless, Authorino) then version-specific
prerequisites and OpenShift AI. Exits 1 on failure.
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


def _install_common_operators(source_dir: str, kubeconfig: str) -> bool:
    info("Phase 1: Installing Node Feature Discovery operator")
    if not apply_manifest(f"{source_dir}/nfd-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv("openshift-nfd", "nfd", kubeconfig, timeout=600):
        return False

    info("Phase 2: Creating NFD operand")
    if not apply_manifest(f"{source_dir}/nfd-operand.yaml", kubeconfig):
        return False
    if not wait_for_condition(
        "NodeFeatureDiscovery",
        "nfd-instance",
        "openshift-nfd",
        "Available",
        kubeconfig,
    ):
        return False

    info("Phase 3: Installing NVIDIA GPU operator")
    if not apply_manifest(f"{source_dir}/nvidia-gpu-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv("nvidia-gpu-operator", "gpu-operator", kubeconfig, timeout=600):
        return False

    info("Phase 4: Creating GPU ClusterPolicy")
    if not apply_manifest(f"{source_dir}/nvidia-gpu-cluster-policy.yaml", kubeconfig):
        return False
    if not wait_for_condition(
        "ClusterPolicy",
        "gpu-cluster-policy",
        "nvidia-gpu-operator",
        "Ready",
        kubeconfig,
    ):
        return False

    info("Phase 5: Installing OpenShift Serverless operator")
    if not apply_manifest(f"{source_dir}/serverless-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv(
        "openshift-serverless", "serverless-operator", kubeconfig, timeout=600
    ):
        return False

    info("Phase 6: Installing Authorino operator")
    if not apply_manifest(f"{source_dir}/authorino-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv(
        "openshift-operators", "authorino-operator", kubeconfig, timeout=600
    ):
        return False

    return True


def _install_v2_operators(version_dir: str, kubeconfig: str) -> bool:
    info("Phase 7: Installing Service Mesh v2 operator")
    if not apply_manifest(
        f"{version_dir}/servicemesh-v2-subscription.yaml", kubeconfig
    ):
        return False
    if not wait_for_csv(
        "openshift-operators", "servicemeshoperator", kubeconfig, timeout=600
    ):
        return False
    return True


def _install_v3_operators(version_dir: str, kubeconfig: str) -> bool:
    info("Phase 7: Installing cert-manager operator")
    if not apply_manifest(f"{version_dir}/cert-manager-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv(
        "cert-manager-operator", "cert-manager", kubeconfig, timeout=600
    ):
        return False

    info("Phase 8: Installing JobSet operator")
    if not apply_manifest(f"{version_dir}/jobset-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv(
        "openshift-jobset-operator", "jobset-operator", kubeconfig, timeout=600
    ):
        return False

    info("Phase 8b: Creating JobSet operand")
    if not apply_manifest(f"{version_dir}/jobset-operand.yaml", kubeconfig):
        return False
    if not wait_for_condition(
        "JobSetOperator",
        "cluster",
        "openshift-jobset-operator",
        "Available",
        kubeconfig,
    ):
        return False

    info("Phase 9: Installing Service Mesh v3 operator")
    if not apply_manifest(f"{version_dir}/servicemesh-subscription.yaml", kubeconfig):
        return False
    if not wait_for_csv(
        "openshift-operators", "servicemeshoperator3", kubeconfig, timeout=600
    ):
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--openshift-ai-version", default="v3", choices=["v2", "v3"])
    args = parser.parse_args()

    cluster = args.cluster_name
    version = args.openshift_ai_version
    configure("apply-ai-workloads")

    info("=== Applying AI workloads to spoke cluster ===")
    info("Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={args.source_dir}")
    info(f"  spoke-kubeconfig={args.spoke_kubeconfig}")
    info(f"  openshift-ai-version={version}")

    source_dir = args.source_dir
    kubeconfig = args.spoke_kubeconfig

    if not _install_common_operators(source_dir, kubeconfig):
        sys.exit(1)

    version_dir = f"{source_dir}/{version}"

    if version == "v2":
        if not _install_v2_operators(version_dir, kubeconfig):
            sys.exit(1)
    else:
        if not _install_v3_operators(version_dir, kubeconfig):
            sys.exit(1)

    info(f"Installing OpenShift AI ({version})")
    if not apply_manifest(f"{version_dir}/openshift-ai-subscription.yaml", kubeconfig):
        sys.exit(1)
    if not wait_for_csv(
        "redhat-ods-operator", "rhods-operator", kubeconfig, timeout=900
    ):
        sys.exit(1)

    if version == "v3":
        info("Creating DataScienceCluster operand")
        if not apply_manifest(f"{version_dir}/openshift-ai-operand.yaml", kubeconfig):
            sys.exit(1)
        if not wait_for_condition(
            "DataScienceCluster",
            "default-dsc",
            "",
            "Ready",
            kubeconfig,
        ):
            sys.exit(1)

    info(f"AI workloads ({version}) successfully applied and ready")
