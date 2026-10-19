"""OpenShift operators that receive cluster-scoped AWS credentials (Manual credentials mode).

Mirrors COMPONENTS in fleet-cluster-scaffold src/scaffold/providers/aws_policies.py. Each
component's Crossplane AccessKey writes Secret <cluster>-<key>-credentials-raw (username/password)
in the cluster namespace; the pipeline turns them into Secrets in <namespace>/<secret> on the spoke.
"""

from typing import NamedTuple


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
