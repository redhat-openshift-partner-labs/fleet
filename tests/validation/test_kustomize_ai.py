"""Validate the AI tier Kustomize manifests and app-of-apps structure.

These tests run 'kustomize build' against each deployment phase and the
parent app-of-apps directory. They verify that every phase produces the
expected Kubernetes resources without requiring a live cluster. Requires
the 'kustomize' binary on PATH.

The AI tier deploys in four phases, each as a separate ArgoCD Application:
  Phase 1: NFD (Node Feature Discovery) -- detects GPU hardware
  Phase 2: NVIDIA GPU Operator -- installs drivers and device plugin
  Phase 3: Dependencies -- Service Mesh, Serverless, Authorino (required by RHOAI)
  Phase 4: RHOAI (Red Hat OpenShift AI) -- ML platform with KServe, dashboard, etc.
"""

import subprocess
from pathlib import Path

import yaml

WORKLOADS_AI = Path("workloads/ai")
PHASE_1 = WORKLOADS_AI / "phase-1-nfd"
PHASE_2 = WORKLOADS_AI / "phase-2-gpu"
PHASE_3_DEPS = WORKLOADS_AI / "phase-3-deps"
PHASE_4 = WORKLOADS_AI / "phase-4-rhoai"


def _kustomize_build(path: Path):
    """Run 'kustomize build' and return parsed YAML documents.

    Captures stdout in memory (no files written to disk) and parses the
    merged YAML output into a list of resource dictionaries.
    """
    result = subprocess.run(
        ["kustomize", "build", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


class TestPhase1NFD:
    """Validate NFD operator manifests (Namespace, OperatorGroup, Subscription,
    and the NodeFeatureDiscovery operand that triggers node GPU labeling)."""

    def test_kustomize_build(self):
        _kustomize_build(PHASE_1)

    def test_expected_kinds(self):
        docs = _kustomize_build(PHASE_1)
        kinds = {d["kind"] for d in docs}
        expected = {"Namespace", "OperatorGroup", "Subscription", "NodeFeatureDiscovery"}
        assert expected <= kinds, f"Missing kinds: {expected - kinds}"

    def test_namespace(self):
        docs = _kustomize_build(PHASE_1)
        ns = {d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"}
        assert "openshift-nfd" in ns


class TestPhase2GPU:
    """Validate NVIDIA GPU Operator manifests. The ClusterPolicy CR triggers
    driver installation, device plugin, DCGM, and toolkit DaemonSets."""

    def test_kustomize_build(self):
        _kustomize_build(PHASE_2)

    def test_expected_kinds(self):
        docs = _kustomize_build(PHASE_2)
        kinds = {d["kind"] for d in docs}
        expected = {"Namespace", "OperatorGroup", "Subscription", "ClusterPolicy"}
        assert expected <= kinds, f"Missing kinds: {expected - kinds}"

    def test_namespace(self):
        docs = _kustomize_build(PHASE_2)
        ns = {d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"}
        assert "nvidia-gpu-operator" in ns


class TestPhase3Deps:
    """Validate RHOAI dependency operators: Service Mesh (Istio), Serverless
    (Knative), and Authorino (authorization). These must be installed before
    RHOAI so that KServe can configure its serving infrastructure."""

    def test_kustomize_build(self):
        _kustomize_build(PHASE_3_DEPS)

    def test_expected_kinds(self):
        docs = _kustomize_build(PHASE_3_DEPS)
        kinds = {d["kind"] for d in docs}
        expected = {"Namespace", "OperatorGroup", "Subscription"}
        assert expected <= kinds, f"Missing kinds: {expected - kinds}"

    def test_namespaces(self):
        """Service Mesh uses istio-system, Serverless needs its own namespace."""
        docs = _kustomize_build(PHASE_3_DEPS)
        ns = {d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"}
        assert "istio-system" in ns
        assert "openshift-serverless" in ns

    def test_subscriptions(self):
        """All three dependency operators must have Subscription resources."""
        docs = _kustomize_build(PHASE_3_DEPS)
        subs = {d["metadata"]["name"] for d in docs if d["kind"] == "Subscription"}
        assert "servicemeshoperator" in subs
        assert "serverless-operator" in subs
        assert "authorino-operator" in subs


class TestPhase4RHOAI:
    """Validate RHOAI operator and DataScienceCluster operand. The DSC
    configures which RHOAI components are Managed vs Removed."""

    def test_kustomize_build(self):
        _kustomize_build(PHASE_4)

    def test_expected_kinds(self):
        docs = _kustomize_build(PHASE_4)
        kinds = {d["kind"] for d in docs}
        expected = {"Namespace", "OperatorGroup", "Subscription", "DataScienceCluster"}
        assert expected <= kinds, f"Missing kinds: {expected - kinds}"

    def test_namespace(self):
        docs = _kustomize_build(PHASE_4)
        ns = {d["metadata"]["name"] for d in docs if d["kind"] == "Namespace"}
        assert "redhat-ods-operator" in ns

    def test_dsc_api_version(self):
        """RHOAI 2.x uses the v1 API; v2 is only available in RHOAI 3.x."""
        docs = _kustomize_build(PHASE_4)
        dsc = [d for d in docs if d["kind"] == "DataScienceCluster"][0]
        assert dsc["apiVersion"] == "datasciencecluster.opendatahub.io/v1"

    def test_rhoai_operatorgroup_all_namespaces(self):
        """RHOAI requires AllNamespaces install mode. Setting targetNamespaces
        causes the CSV to fail with 'OwnNamespace InstallModeType not supported'."""
        docs = _kustomize_build(PHASE_4)
        og = [d for d in docs if d["kind"] == "OperatorGroup"][0]
        assert "targetNamespaces" not in og.get("spec", {}), \
            "RHOAI OperatorGroup must use AllNamespaces mode"


class TestAppOfApps:
    """Validate the parent kustomization that produces four ArgoCD Application
    resources. Each Application points to one phase subdirectory and uses
    sync-wave annotations to define deployment order."""

    def test_kustomize_build(self):
        _kustomize_build(WORKLOADS_AI)

    def test_produces_four_applications(self):
        """The parent must produce exactly four child Applications."""
        docs = _kustomize_build(WORKLOADS_AI)
        apps = [d for d in docs if d["kind"] == "Application"]
        assert len(apps) == 4

    def test_application_sync_wave_ordering(self):
        """Sync waves must enforce: NFD -> GPU -> Deps -> RHOAI. ArgoCD
        processes lower waves first, ensuring operator dependencies are
        installed before their dependents."""
        docs = _kustomize_build(WORKLOADS_AI)
        apps = [d for d in docs if d["kind"] == "Application"]
        waves = {
            d["metadata"]["name"]: int(
                d["metadata"].get("annotations", {}).get(
                    "argocd.argoproj.io/sync-wave", "0"
                )
            )
            for d in apps
        }
        assert waves["ai-phase-1-nfd"] < waves["ai-phase-2-gpu"]
        assert waves["ai-phase-2-gpu"] < waves["ai-phase-3-deps"]
        assert waves["ai-phase-3-deps"] < waves["ai-phase-4-rhoai"]
