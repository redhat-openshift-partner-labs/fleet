"""OpenShift operators that receive cluster-scoped AWS credentials (Manual credentials mode).

Each operator's Crossplane AccessKey writes a raw Secret (username/password) in the cluster
namespace; the pipeline turns them into Secrets in the operator's target namespace/Secret on the
spoke. The hub's IAM resources for a cluster are found by the ownership label; only the installer
set and the BYO node roles also keep fixed names (iam_targets).

discover_components reads the operator set from the cluster's own AccessKeys on the hub: every
operator AccessKey carries the three openshiftpartnerlabs.com target annotations the scaffold
writes (TARGET_ANNOTATIONS); the installer AccessKey <cluster>-access-key carries none and is
skipped.
"""

import json
import subprocess
from typing import NamedTuple

# Literal placeholders in scaffold-rendered policies (aws_policies.py); they match nothing until
# scope-aws-credentials substitutes the installed cluster's infra ID and VPC ID.
INFRA_ID_PLACEHOLDER = "INFRA_ID_PLACEHOLDER"
VPC_ID_PLACEHOLDER = "VPC_ID_PLACEHOLDER"

# Ownership label the scaffold puts on every overlay resource (value: cluster name)
CLUSTER_LABEL = "openshiftpartnerlabs.com/cluster"

# Deletion order: attachments and keys before the policies and users they reference
_IAM_KINDS = ("userpolicyattachment", "accesskey", "policy", "user", "role")
_IAM_RESOURCES = ",".join(
    f"{r}.iam.aws.upbound.io"
    for r in ("userpolicyattachments", "accesskeys", "policies", "users", "roles")
)

# Written by fleet-cluster-scaffold on every operator AccessKey; the installer AccessKey has none.
ANNOTATION_CREDENTIALS_REQUEST = "openshiftpartnerlabs.com/credentials-request"
ANNOTATION_TARGET_NAMESPACE = "openshiftpartnerlabs.com/target-namespace"
# The value is an annotation key, not a credential (bandit B105 keys on the name)
ANNOTATION_TARGET_SECRET = "openshiftpartnerlabs.com/target-secret"  # nosec B105
TARGET_ANNOTATIONS = (
    ANNOTATION_CREDENTIALS_REQUEST,
    ANNOTATION_TARGET_NAMESPACE,
    ANNOTATION_TARGET_SECRET,
)
REGENERATE = "regenerate the overlay with the current fleet-cluster-scaffold"


class DiscoveryError(RuntimeError):
    """The cluster's IAM resources could not be listed, or the overlay predates the annotations."""


class OperatorCredential(NamedTuple):
    credentials_request: str  # log lines only
    namespace: str  # spoke target namespace
    secret: str  # spoke target Secret
    raw_secret: str  # hub Secret written by the AccessKey (spec.writeConnectionSecretToRef.name)
    access_key: str  # AccessKey name, for messages


def installer_access_key_name(cluster: str) -> str:
    return f"{cluster}-access-key"


def manifests_secret_name(cluster: str) -> str:
    """Secret referenced by ClusterDeployment.spec.provisioning.manifestsSecretRef."""
    return f"{cluster}-cloud-credentials-manifests"


def discover_components(cluster: str) -> list[OperatorCredential]:
    """Operator credentials of a scoped cluster, read from its labelled AccessKeys.

    Skips installer_access_key_name(cluster); sorted by access_key. DiscoveryError when oc
    fails, when any other labelled AccessKey lacks a target annotation (a hand-edited or
    pre-annotation overlay), or when no operator AccessKey is left.
    """
    result = subprocess.run(
        [
            "oc",
            "get",
            "accesskeys.iam.aws.upbound.io",
            "-l",
            f"{CLUSTER_LABEL}={cluster}",
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DiscoveryError(
            f"AccessKey lookup failed for {cluster}: {result.stderr.strip()}"
        )
    installer = installer_access_key_name(cluster)
    operators: list[OperatorCredential] = []
    for item in json.loads(result.stdout).get("items", []):
        name = item["metadata"]["name"]
        if name == installer:
            continue
        annotations = item["metadata"].get("annotations") or {}
        if not all(annotations.get(key) for key in TARGET_ANNOTATIONS):
            raise DiscoveryError(
                f"AccessKey {name} lacks target annotations; {REGENERATE}"
            )
        operators.append(
            OperatorCredential(
                credentials_request=annotations[ANNOTATION_CREDENTIALS_REQUEST],
                namespace=annotations[ANNOTATION_TARGET_NAMESPACE],
                secret=annotations[ANNOTATION_TARGET_SECRET],
                raw_secret=item["spec"]["writeConnectionSecretToRef"]["name"],
                access_key=name,
            )
        )
    if not operators:
        raise DiscoveryError(
            f"no operator AccessKeys carry target annotations for {cluster}; {REGENERATE}"
        )
    return sorted(operators, key=lambda c: c.access_key)


def iam_targets(cluster: str) -> list[str]:
    """TYPE/NAME of the IAM resources a cluster owns under fixed names.

    The installer attachment, access key, policy and user, plus the BYO node roles (6).
    Operator resources carry only the ownership label and come from labelled_iam_targets.
    Attachments and access keys precede the policies and users they reference.
    """
    return [
        f"userpolicyattachment.iam/{cluster}-policy-attachment",
        f"accesskey.iam/{cluster}-access-key",
        f"policy.iam/{cluster}-openshift4installerpolicy",
        f"user.iam/{cluster}-ocp-installer",
        f"role.iam/{cluster}-master-role",
        f"role.iam/{cluster}-worker-role",
    ]


def labelled_iam_targets(cluster: str) -> list[str]:
    """TYPE/NAME (kind.iam/name) of every IAM resource carrying the cluster's ownership label.

    DiscoveryError if oc fails: operator resources are known only by label, so a failed lookup
    must not pass for an empty cluster.
    """
    result = subprocess.run(
        ["oc", "get", _IAM_RESOURCES, "-l", f"{CLUSTER_LABEL}={cluster}", "-o", "name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DiscoveryError(
            f"IAM label lookup failed for {cluster}: {result.stderr.strip()}"
        )
    # oc prints kind.iam.aws.upbound.io/name; iam_targets uses kind.iam/name
    return [
        f"{ref.split('.', 1)[0]}.iam/{ref.split('/', 1)[1]}"
        for ref in result.stdout.split()
    ]


def all_iam_targets(cluster: str) -> list[str]:
    """iam_targets plus the labelled resources, de-duplicated, in deletion order.

    Propagates DiscoveryError from labelled_iam_targets.
    """
    targets = list(dict.fromkeys(iam_targets(cluster) + labelled_iam_targets(cluster)))
    return sorted(targets, key=lambda t: _IAM_KINDS.index(t.split(".", 1)[0]))
