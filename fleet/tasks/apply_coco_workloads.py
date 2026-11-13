"""Install OpenShift sandboxed containers with peer pods on the spoke (coco tier, AWS).

CLI: fleet-apply-coco-workloads --cluster-name NAME --source-dir DIR --spoke-kubeconfig PATH
       --podvm-instance-type TYPE --region R --vpc-id V --subnet-id S --sg-ids IDS --ami-id AMI
       --podvm-payload DIGEST [--kataconfig-timeout-seconds 5400]
Order on the spoke: Namespace, Secret peer-pods-secret, ConfigMap osc-feature-gates, ConfigMap
peer-pods-cm, OperatorGroup and Subscription, CSV Succeeded, pairing check, KataConfig,
completion. The Secret exists before the operator runs, so the operator creates no
CredentialsRequest (Manual credentials mode would not fulfil one). The peer-pods credential is
the discovered credential with delivery post-provision whose target Secret is peer-pods-secret;
its values are read from the raw Secret on the hub, go to oc through stdin only and are never
logged. The network values come from prepare-podvm-aws; the AMI and the digest of the disk
image it was built from come from build-podvm-image-aws. The pairing check reads the installed
ClusterServiceVersion of the Subscription and fails when its disk image has another digest.
Exits 1 on any failure.
"""

import argparse
import binascii
import json
import subprocess
import sys
import time

from fleet.tasks._aws_components import (
    CLUSTER_LABEL,
    DELIVERY_POST_PROVISION,
    PEER_PODS_SECRET,
    REGENERATE,
    DiscoveryError,
    OperatorCredential,
    discover_components,
    read_raw_credentials,
)
from fleet.tasks._log import configure, error, info
from fleet.tasks._operator_catalog import check_operator_catalog
from fleet.tasks._podvm_image_aws import PodVMImageError, disk_image
from fleet.tasks.apply_virt_workloads import apply_manifest, wait_for_csv

# Names fixed by the operator and its documentation; the first four also appear in workloads/coco
OSC_NAMESPACE = "openshift-sandboxed-containers-operator"
OSC_PACKAGE = "sandboxed-containers-operator"
FEATURE_GATES_CONFIGMAP = "osc-feature-gates"
KATACONFIG = "example-kataconfig"
PEER_PODS_CONFIGMAP = "peer-pods-cm"
CAA_DAEMONSET = "osc-caa-ds"
RUNTIME_CLASS = "kata-remote"

_POLL_SECONDS = 30


def peer_pods_credential(cluster: str) -> OperatorCredential:
    """The discovered credential with delivery post-provision and secret PEER_PODS_SECRET.

    DiscoveryError unless exactly one exists.
    """
    found = [
        c
        for c in discover_components(cluster)
        if c.delivery == DELIVERY_POST_PROVISION and c.secret == PEER_PODS_SECRET
    ]
    if len(found) != 1:
        raise DiscoveryError(
            f"expected 1 peer-pods credential for {cluster}, found {len(found)}; {REGENERATE}"
        )
    return found[0]


def peer_pods_config(cluster: str, args: argparse.Namespace) -> dict[str, str]:
    """The 14 peer-pods-cm keys.

    No INITDATA: no attestation service is deployed. The operator rewrites DISABLECVM on every
    reconcile from the confidential feature gate (workloads/coco/feature-gates.yaml).
    """
    return {
        "CLOUD_PROVIDER": "aws",
        "VXLAN_PORT": "9000",
        "PROXY_TIMEOUT": "8m",
        "PODVM_INSTANCE_TYPE": args.podvm_instance_type,
        "PODVM_INSTANCE_TYPES": args.podvm_instance_type,
        # A non-empty AMI ID keeps the operator from building a pod VM image itself
        "PODVM_AMI_ID": args.ami_id,
        "AWS_REGION": args.region,
        "AWS_SUBNET_ID": args.subnet_id,
        "AWS_VPC_ID": args.vpc_id,
        "AWS_SG_IDS": args.sg_ids,
        # The peer-pods policy allows launching and terminating instances with this tag only
        "TAGS": f"{CLUSTER_LABEL}={cluster}",
        "PEERPODS_LIMIT_PER_NODE": "10",
        "ROOT_VOLUME_SIZE": "6",
        "DISABLECVM": "false",
    }


def apply_object(obj: dict, kubeconfig: str) -> bool:
    """`oc apply -f - --kubeconfig=...` with json.dumps(obj) on stdin. Logs kind/name only."""
    target = f"{obj['kind']}/{obj['metadata']['name']}"
    info(f"Applying {target}")
    result = subprocess.run(
        ["oc", "apply", "-f", "-", f"--kubeconfig={kubeconfig}"],
        input=json.dumps(obj),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to apply {target}: {result.stderr.strip()}")
        return False
    info(f"  -> Applied: {result.stdout.strip()}")
    return True


def _exists(kubeconfig: str, *resource: str) -> bool:
    result = subprocess.run(
        ["oc", "get", *resource, "-o", "name", f"--kubeconfig={kubeconfig}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def podvm_pairing(payload: str, kubeconfig: str) -> bool:
    """True when the installed operator names the disk image the pod VM AMI was built from.

    payload is the digest that build-podvm-image-aws returned. The installed version is
    status.installedCSV of the Subscription; its disk image is selected from spec.relatedImages
    by disk_image. Each failure logs one error line.
    """
    info("Checking the pod VM image against the installed operator")
    result = subprocess.run(
        [
            "oc",
            "get",
            "subscription.operators.coreos.com",
            OSC_PACKAGE,
            "-n",
            OSC_NAMESPACE,
            "-o",
            "jsonpath={.status.installedCSV}",
            f"--kubeconfig={kubeconfig}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read Subscription {OSC_PACKAGE}: {result.stderr.strip()}")
        return False
    csv = result.stdout.strip()
    if not csv:
        error(f"Subscription {OSC_PACKAGE} has no installedCSV; re-run post-provision")
        return False
    result = subprocess.run(
        [
            "oc",
            "get",
            "clusterserviceversion",
            csv,
            "-n",
            OSC_NAMESPACE,
            "-o",
            "json",
            f"--kubeconfig={kubeconfig}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read ClusterServiceVersion {csv}: {result.stderr.strip()}")
        return False
    try:
        related = json.loads(result.stdout).get("spec", {}).get("relatedImages") or []
        image, digest = disk_image([entry.get("image", "") for entry in related])
    except (json.JSONDecodeError, PodVMImageError) as exc:
        error(f"ClusterServiceVersion {csv}: {exc}")
        return False
    if digest != payload:
        error(
            f"The pod VM AMI was built from disk image {payload}; {csv} uses {image}; "
            "re-run post-provision"
        )
        return False
    info(f"  -> {csv} uses the disk image the pod VM AMI was built from")
    return True


def _kataconfig_progress(name: str, kubeconfig: str) -> tuple[bool, list[str]]:
    """(installed on every node, nodes that failed to install).

    A failed or unparsable oc answer is (False, []): the spoke API restarts when control-plane
    nodes reboot (compact and sno).
    """
    result = subprocess.run(
        ["oc", "get", "kataconfig", name, "-o", "json", f"--kubeconfig={kubeconfig}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, []
    try:
        status = json.loads(result.stdout).get("status") or {}
    except json.JSONDecodeError:
        return False, []
    nodes = status.get("kataNodes") or {}
    in_progress = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
    count = nodes.get("nodeCount", 0)
    ready = nodes.get("readyNodeCount", 0)
    info(f"  -> KataConfig {name}: {ready}/{count} node(s) ready")
    installed = in_progress.get("InProgress") == "False" and 0 < count == ready
    return installed, list(nodes.get("failedToInstall") or [])


def wait_for_kataconfig(name: str, kubeconfig: str, timeout: int) -> bool:
    """Poll every 30 s until the KataConfig is installed on every node and peer pods are usable.

    Installed: condition InProgress is False and kataNodes.readyNodeCount == nodeCount > 0.
    Usable: DaemonSet CAA_DAEMONSET in OSC_NAMESPACE and RuntimeClass RUNTIME_CLASS exist. A
    non-empty kataNodes.failedToInstall returns False at once; the timeout covers both parts.
    """
    info(f"Waiting for KataConfig {name} (timeout: {timeout}s)")
    deadline = time.monotonic() + timeout
    while True:
        installed, failed = _kataconfig_progress(name, kubeconfig)
        if failed:
            error(f"KataConfig {name} failed to install on: {', '.join(failed)}")
            return False
        if (
            installed
            and _exists(kubeconfig, "daemonset", CAA_DAEMONSET, "-n", OSC_NAMESPACE)
            and _exists(kubeconfig, "runtimeclass", RUNTIME_CLASS)
        ):
            info(f"  -> KataConfig {name} is installed; {RUNTIME_CLASS} is available")
            return True
        if time.monotonic() >= deadline:
            error(f"Timed out after {timeout}s waiting for KataConfig {name}")
            return False
        time.sleep(_POLL_SECONDS)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--spoke-kubeconfig", required=True)
    parser.add_argument("--podvm-instance-type", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--vpc-id", required=True)
    parser.add_argument("--subnet-id", required=True)
    parser.add_argument("--sg-ids", required=True)
    parser.add_argument("--ami-id", required=True)
    parser.add_argument("--podvm-payload", required=True)
    parser.add_argument("--kataconfig-timeout-seconds", type=int, default=5400)
    return parser.parse_args()


def _credential_secret(cluster: str) -> dict:
    """The Secret the operator reads its AWS credential from, built from the hub's raw Secret."""
    credential = peer_pods_credential(cluster)
    info(f"Reading {credential.raw_secret} ({credential.credentials_request})...")
    key_id, secret = read_raw_credentials(cluster, credential)
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": credential.secret, "namespace": credential.namespace},
        "type": "Opaque",
        "stringData": {"AWS_ACCESS_KEY_ID": key_id, "AWS_SECRET_ACCESS_KEY": secret},
    }


def main() -> None:
    args = _parse_args()
    cluster = args.cluster_name
    source_dir = args.source_dir
    kubeconfig = args.spoke_kubeconfig
    configure("apply-coco-workloads")

    info("=== Applying confidential containers workloads to spoke cluster ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  source-dir={source_dir}")
    info(f"  spoke-kubeconfig={kubeconfig}")
    info(f"  podvm-instance-type={args.podvm_instance_type}")
    info(f"  region={args.region} vpc-id={args.vpc_id} subnet-id={args.subnet_id}")
    info(f"  sg-ids={args.sg_ids} ami-id={args.ami_id}")
    info(f"  podvm-payload={args.podvm_payload}")

    if not args.podvm_instance_type:
        error(f"podvm-instance-type is empty for {cluster}; {REGENERATE}")
        sys.exit(1)

    available, reason = check_operator_catalog(
        OSC_PACKAGE, "stable", "redhat-operators", kubeconfig
    )
    if not available:
        error(f"OpenShift sandboxed containers operator is unavailable: {reason}")
        sys.exit(1)

    try:
        credential_secret = _credential_secret(cluster)
    except subprocess.CalledProcessError as exc:
        error(f"Failed to read the peer-pods credential: {(exc.stderr or '').strip()}")
        sys.exit(1)
    except (DiscoveryError, KeyError, binascii.Error, ValueError) as exc:
        error(f"Failed to read the peer-pods credential: {exc}")
        sys.exit(1)

    peer_pods_cm = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": PEER_PODS_CONFIGMAP, "namespace": OSC_NAMESPACE},
        "data": peer_pods_config(cluster, args),
    }
    # Each step logs its own error; the Secret and both ConfigMaps precede the operator
    steps = (
        lambda: apply_manifest(f"{source_dir}/namespace.yaml", kubeconfig),
        lambda: apply_object(credential_secret, kubeconfig),
        lambda: apply_manifest(f"{source_dir}/feature-gates.yaml", kubeconfig),
        lambda: apply_object(peer_pods_cm, kubeconfig),
        lambda: apply_manifest(f"{source_dir}/subscription.yaml", kubeconfig),
        lambda: wait_for_csv(OSC_NAMESPACE, OSC_PACKAGE, kubeconfig, timeout=900),
        lambda: podvm_pairing(args.podvm_payload, kubeconfig),
        lambda: apply_manifest(f"{source_dir}/kataconfig.yaml", kubeconfig),
        lambda: wait_for_kataconfig(
            KATACONFIG, kubeconfig, args.kataconfig_timeout_seconds
        ),
    )
    for step in steps:
        if not step():
            sys.exit(1)

    info("Confidential containers workloads applied; peer pods are ready")
