"""Checks shared by the tools of the test-vcluster pipeline.

The tools create and delete hub resources by the name of the test. These checks
stop a tool when the name belongs to a real cluster, and tell a namespace that a
test created from one that existed before.
"""

import json
import subprocess
from typing import Any

# seed-test-vcluster sets this label, with the name of the test as its value, on the
# namespace it creates. delete-test-vcluster deletes only a namespace that carries it.
OWNER_LABEL = "fleet-test-vcluster"

ABSENT, OWNED, FOREIGN = "absent", "owned", "foreign"


def _get(kind: str, name: str, namespace: str | None, output: str) -> str:
    """Output of `oc get`, empty when the object does not exist."""
    cmd = ["oc", "get", kind, name, "--ignore-not-found=true"]
    if namespace:
        cmd += ["-n", namespace]
    result = subprocess.run(cmd + ["-o", output], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cannot read {kind} {name}: {result.stderr.strip()}")
    return result.stdout.strip()


def _labels(kind: str, name: str) -> dict[str, Any] | None:
    """Labels of a cluster-scoped object, or None when it does not exist."""
    document = _get(kind, name, None, "json")
    if not document:
        return None
    return json.loads(document)["metadata"].get("labels") or {}


def refusal(cluster: str) -> str | None:
    """Reason why `cluster` is not the name of a test vCluster, or None.

    A name is refused when a ClusterDeployment has it, when its ManagedCluster does
    not carry cloud=vcluster, and when the hub cannot be read.
    """
    try:
        if _get("clusterdeployment", cluster, cluster, "name"):
            return f"ClusterDeployment {cluster} exists in namespace {cluster}"
        labels = _labels("managedcluster", cluster)
    except RuntimeError as exc:
        return str(exc)
    if labels is not None and labels.get("cloud") != "vcluster":
        return f"ManagedCluster {cluster} does not carry the label cloud=vcluster"
    return None


def namespace_state(cluster: str) -> str:
    """ABSENT, OWNED when a test created the namespace `cluster`, or FOREIGN."""
    labels = _labels("namespace", cluster)
    if labels is None:
        return ABSENT
    return OWNED if labels.get(OWNER_LABEL) == cluster else FOREIGN


def has_vcluster(cluster: str, namespace: str) -> bool:
    """True when the Secret vc-NAME of the vCluster exists. Its data is not read."""
    return bool(_get("secret", f"vc-{cluster}", namespace, "name"))
