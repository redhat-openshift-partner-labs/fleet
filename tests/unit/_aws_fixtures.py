"""Shared test data for the scoped-AWS credential tasks.

RENDERING is one fleet-cluster-scaffold rendering of a scoped overlay's AccessKeys; the refresh
command is under "Fixture refresh" in the PRD
(.taskmaster/docs/prd-discover-aws-components-from-annotations.txt). The hand-written payloads
use two operators so that no test depends on how many operators the scaffold defines.
"""

import json
import subprocess
from pathlib import Path

from fleet.tasks._aws_components import (
    ANNOTATION_CREDENTIALS_REQUEST,
    ANNOTATION_TARGET_NAMESPACE,
    ANNOTATION_TARGET_SECRET,
    CLUSTER_LABEL,
    OperatorCredential,
)

RENDERING = Path(__file__).parent.parent / "data" / "scoped-aws-access-keys.json"

# Two operators, not six: the code must not care how many there are.
OPERATORS = [
    OperatorCredential(
        "openshift-ingress",
        "openshift-ingress-operator",
        "cloud-credentials",
        "test-cluster-ingress-credentials-raw",
        "test-cluster-ingress-access-key",
    ),
    OperatorCredential(
        "openshift-machine-api-aws",
        "openshift-machine-api",
        "aws-cloud-credentials",
        "test-cluster-machine-api-credentials-raw",
        "test-cluster-machine-api-access-key",
    ),
]


def access_key_item(
    cluster,
    key,
    credentials_request=None,
    namespace=None,
    secret=None,
    annotated=True,
):
    """One AccessKey as `oc get -o json` lists it; key None builds the installer AccessKey."""
    if key is None:
        name = f"{cluster}-access-key"
        raw_secret = "aws-credentials-raw"
        user = f"{cluster}-ocp-installer"
    else:
        name = f"{cluster}-{key}-access-key"
        raw_secret = f"{cluster}-{key}-credentials-raw"
        user = f"{cluster}-{key}"
    metadata = {
        "labels": {CLUSTER_LABEL: cluster},
        "name": name,
        "namespace": cluster,
    }
    if key is not None and annotated:
        metadata["annotations"] = {
            ANNOTATION_CREDENTIALS_REQUEST: credentials_request or f"openshift-{key}",
            ANNOTATION_TARGET_NAMESPACE: namespace or f"openshift-{key}-operator",
            ANNOTATION_TARGET_SECRET: secret or "cloud-credentials",
        }
    return {
        "apiVersion": "iam.aws.upbound.io/v1beta1",
        "kind": "AccessKey",
        "metadata": metadata,
        "spec": {
            "forProvider": {"userRef": {"name": user}},
            "providerConfigRef": {"name": "default"},
            "writeConnectionSecretToRef": {"name": raw_secret, "namespace": cluster},
        },
    }


def access_keys_payload(*items):
    """CompletedProcess(rc=0, stdout=json List of items)."""
    return subprocess.CompletedProcess(
        [],
        returncode=0,
        stdout=json.dumps({"apiVersion": "v1", "kind": "List", "items": list(items)}),
        stderr="",
    )


def iam_targets_for(cluster, operators=OPERATORS):
    """Installer set + one set per operator + node roles, in deletion order (what all_iam_targets returns)."""
    keys = [
        o.access_key.removeprefix(f"{cluster}-").removesuffix("-access-key")
        for o in operators
    ]
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
