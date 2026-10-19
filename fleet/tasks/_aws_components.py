"""OpenShift operators that receive cluster-scoped AWS credentials (Manual credentials mode).

Mirrors COMPONENTS in fleet-cluster-scaffold src/scaffold/providers/aws_policies.py. Each
component's Crossplane AccessKey writes Secret <cluster>-<key>-credentials-raw (username/password)
in the cluster namespace; the pipeline turns them into Secrets in <namespace>/<secret> on the spoke.
"""

from typing import NamedTuple

# Literal placeholders in scaffold-rendered policies (aws_policies.py); they match nothing until
# scope-aws-credentials substitutes the installed cluster's infra ID and VPC ID.
INFRA_ID_PLACEHOLDER = "INFRA_ID_PLACEHOLDER"
VPC_ID_PLACEHOLDER = "VPC_ID_PLACEHOLDER"


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


def manifests_secret_name(cluster: str) -> str:
    """Secret referenced by ClusterDeployment.spec.provisioning.manifestsSecretRef."""
    return f"{cluster}-cloud-credentials-manifests"


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
