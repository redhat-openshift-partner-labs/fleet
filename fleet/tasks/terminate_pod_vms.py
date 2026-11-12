"""Terminate the peer pod VMs of a coco cluster before the cluster is uninstalled.

CLI: fleet-terminate-pod-vms --cluster-name NAME [--timeout-seconds 600]
Pod VMs carry only the ownership tag openshiftpartnerlabs.com/cluster=<name>, which
`openshift-install destroy` does not look for; a pod VM left running keeps a network interface
in the cluster subnet. The task acts only when the ManagedCluster tier label is coco and the
cluster is installed. It deletes the peer-pods AccessKey first, so cloud-api-adaptor can launch
nothing new, then terminates the pod VMs with the installer credential and polls every 10 s
until none is left. Exits 1 on any failure, before the deprovision pipeline deletes anything
else; instances left at the timeout are logged one per line.
"""

import argparse
import binascii
import subprocess
import sys
import time
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from fleet.tasks._aws_binding import installed_cluster_facts
from fleet.tasks._aws_components import (
    PEER_PODS_SECRET,
    TIER_COCO,
    DiscoveryError,
    post_provision_credentials,
)
from fleet.tasks._log import configure, error, info
from fleet.tasks._podvm_aws import ec2_client, pod_vm_instances, terminate

_POLL_SECONDS = 10


def _tier(cluster: str) -> str:
    """The ManagedCluster tier label; "" when the ManagedCluster or the label is absent."""
    result = subprocess.run(
        [
            "oc",
            "get",
            "managedcluster",
            cluster,
            "--ignore-not-found",
            "-o",
            "jsonpath={.metadata.labels.tier}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error(f"Failed to read the tier label of {cluster}: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def _delete_peer_pods_access_keys(cluster: str) -> None:
    """Delete the AccessKey behind peer-pods-secret and wait until Crossplane removed it."""
    for credential in post_provision_credentials(cluster):
        if credential.secret != PEER_PODS_SECRET:
            continue
        info(f"Deleting peer-pods AccessKey {credential.access_key}...")
        result = subprocess.run(
            [
                "oc",
                "delete",
                "accesskey.iam.aws.upbound.io",
                credential.access_key,
                "--ignore-not-found=true",
                "--wait=true",
                "--timeout=120s",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error(
                f"peer-pods AccessKey {credential.access_key} not deleted: "
                f"{result.stderr.strip()}"
            )
            sys.exit(1)


def _terminate_until_gone(ec2: Any, cluster: str, infra_id: str, timeout: int) -> None:
    """Terminate every pod VM, new ones included, and wait until none is listed."""
    elapsed = 0
    while True:
        instances = pod_vm_instances(ec2, cluster, infra_id)
        if not instances:
            info(f"No pod VMs left (elapsed: {elapsed}s)")
            return
        pending = sorted(
            i for i, state in instances.items() if state != "shutting-down"
        )
        if pending:
            info(f"Terminating {len(pending)} pod VM(s): {', '.join(pending)}")
            terminate(ec2, pending)
        if elapsed >= timeout:
            break
        time.sleep(_POLL_SECONDS)
        elapsed += _POLL_SECONDS
        info(f"  Poll [{elapsed}s/{timeout}s]: {len(instances)} pod VM(s) not gone yet")

    for instance, state in sorted(instances.items()):
        error(f"pod VM {instance} is still {state} after {timeout}s")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-name", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    configure("terminate-pod-vms")

    cluster = args.cluster_name
    info("=== Terminating peer pod VMs ===")
    info(f"Parameters:")
    info(f"  cluster-name={cluster}")
    info(f"  timeout={args.timeout_seconds}s")

    tier = _tier(cluster)
    if tier != TIER_COCO:
        info(f"tier '{tier}': no pod VMs to terminate")
        return

    try:
        facts = installed_cluster_facts(cluster)
        if facts is None:
            info("cluster not installed: no pod VMs to terminate")
            return
        infra_id, region, creds_secret = facts
        _delete_peer_pods_access_keys(cluster)
        ec2 = ec2_client(cluster, region, creds_secret)
        _terminate_until_gone(ec2, cluster, infra_id, args.timeout_seconds)
    except subprocess.CalledProcessError as exc:
        error(f"Failed to terminate pod VMs: {exc}: {(exc.stderr or '').strip()}")
        sys.exit(1)
    except (
        DiscoveryError,
        KeyError,
        binascii.Error,
        ClientError,
        BotoCoreError,
    ) as exc:
        error(f"Failed to terminate pod VMs: {exc}")
        sys.exit(1)
