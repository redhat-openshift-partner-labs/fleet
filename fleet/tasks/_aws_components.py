"""OpenShift operators that receive cluster-scoped AWS credentials (Manual credentials mode).

Mirrors COMPONENTS in fleet-cluster-scaffold src/scaffold/providers/aws_policies.py. Each
component's Crossplane AccessKey writes Secret <cluster>-<key>-credentials-raw (username/password)
in the cluster namespace; the pipeline turns them into Secrets in <namespace>/<secret> on the spoke.

discover_components reads the operator set from the cluster's own AccessKeys on the hub: every
operator AccessKey carries the three openshiftpartnerlabs.com target annotations the scaffold
writes (TARGET_ANNOTATIONS); the installer AccessKey <cluster>-access-key carries none and is
skipped.
"""

import json
import subprocess
from typing import NamedTuple

from fleet.tasks._log import warn

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


class Component(NamedTuple):
    key: str
    namespace: str
    secret: str


COMPONENTS: tuple[Component, ...] = (
    Component("machine-api", "openshift-machine-api", "aws-cloud-credentials"),
    Component(
        "cco-iam-ro",
        "openshift-cloud-credential-operator",
        "cloud-credential-operator-iam-ro-creds",
    ),
    Component(
        "image-registry", "openshift-image-registry", "installer-cloud-credentials"
    ),
    Component("ingress", "openshift-ingress-operator", "cloud-credentials"),
    Component("cncc", "openshift-cloud-network-config-controller", "cloud-credentials"),
    Component("ebs-csi", "openshift-cluster-csi-drivers", "ebs-cloud-credentials"),
)


def raw_secret_name(cluster: str, key: str) -> str:
    return f"{cluster}-{key}-credentials-raw"


def access_key_name(cluster: str, key: str) -> str:
    return f"{cluster}-{key}-access-key"


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
    """TYPE/NAME of every Crossplane IAM resource a cluster may own.

    Legacy clusters have only the installer set; scoped clusters add one set per operator and
    the BYO node roles. Attachments and access keys precede the policies and users they reference.
    """
    keys = [c.key for c in COMPONENTS]
    return [
        f"userpolicyattachment.iam/{cluster}-policy-attachment",
        *(f"userpolicyattachment.iam/{cluster}-{k}-attachment" for k in keys),
        f"accesskey.iam/{cluster}-access-key",
        *(f"accesskey.iam/{cluster}-{k}-access-key" for k in keys),
        f"policy.iam/{cluster}-openshift4installerpolicy",
        *(f"policy.iam/{cluster}-{k}-policy" for k in keys),
        f"user.iam/{cluster}-ocp-installer",
        *(f"user.iam/{cluster}-{k}" for k in keys),
        f"role.iam/{cluster}-master-role",
        f"role.iam/{cluster}-worker-role",
    ]


def labelled_iam_targets(cluster: str) -> list[str]:
    """TYPE/NAME (kind.iam/name) of every IAM resource carrying the cluster's ownership label.

    Returns [] if oc fails; callers union this with iam_targets, so known names still apply.
    """
    result = subprocess.run(
        ["oc", "get", _IAM_RESOURCES, "-l", f"{CLUSTER_LABEL}={cluster}", "-o", "name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        warn(f"Label lookup failed, using known names only: {result.stderr.strip()}")
        return []
    # oc prints kind.iam.aws.upbound.io/name; iam_targets uses kind.iam/name
    return [
        f"{ref.split('.', 1)[0]}.iam/{ref.split('/', 1)[1]}"
        for ref in result.stdout.split()
    ]


def all_iam_targets(cluster: str) -> list[str]:
    """iam_targets plus any labelled extras, de-duplicated, in deletion order."""
    targets = list(dict.fromkeys(iam_targets(cluster) + labelled_iam_targets(cluster)))
    return sorted(targets, key=lambda t: _IAM_KINDS.index(t.split(".", 1)[0]))
