from fleet.tasks._aws_components import (
    COMPONENTS,
    access_key_name,
    manifests_secret_name,
    raw_secret_name,
)


def test_resource_names():
    assert raw_secret_name("c1", "ingress") == "c1-ingress-credentials-raw"
    assert access_key_name("c1", "ingress") == "c1-ingress-access-key"
    assert manifests_secret_name("c1") == "c1-cloud-credentials-manifests"


def test_components_match_scaffold_credentials_requests():
    # Must stay in sync with fleet-cluster-scaffold aws_policies.COMPONENTS
    assert {(c.key, c.namespace, c.secret) for c in COMPONENTS} == {
        ("machine-api", "openshift-machine-api", "aws-cloud-credentials"),
        (
            "cco-iam-ro",
            "openshift-cloud-credential-operator",
            "cloud-credential-operator-iam-ro-creds",
        ),
        ("image-registry", "openshift-image-registry", "installer-cloud-credentials"),
        ("ingress", "openshift-ingress-operator", "cloud-credentials"),
        ("cncc", "openshift-cloud-network-config-controller", "cloud-credentials"),
        ("ebs-csi", "openshift-cluster-csi-drivers", "ebs-cloud-credentials"),
    }
