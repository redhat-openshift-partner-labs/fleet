"""Generate cluster overlay directories for the fleet Kustomize structure."""

import os
from dataclasses import dataclass

import yaml


@dataclass
class ClusterParams:
    name: str
    region: str
    tier: str
    environment: str = "development"
    control_plane_type: str = "m7i.4xlarge"
    worker_type: str = "m7i.2xlarge"
    control_plane_replicas: int = 3
    worker_replicas: int = 3
    image_set: str = "img4.21.13-x86-64-appsub"
    zones: list[str] | None = None

    def __post_init__(self) -> None:
        if self.zones is None:
            self.zones = get_default_zones(self.region)


def get_default_zones(region: str) -> list[str]:
    return [f"{region}a", f"{region}b", f"{region}c"]


def generate_hive_patches(params: ClusterParams) -> dict[str, str]:
    n = params.name
    patches: dict[str, str] = {}

    patches["kustomization.yaml"] = yaml.dump(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": n,
            "resources": ["../../../cluster-templates/aws-ha/base/hive"],
            "patches": [
                {"path": "patches/install-config.yaml"},
                {
                    "target": {
                        "kind": "Secret",
                        "name": "cluster-placeholder-install-config",
                    },
                    "path": "patches/install-config-meta.yaml",
                },
                {
                    "target": {"kind": "Namespace", "name": "cluster-placeholder"},
                    "path": "patches/namespace.yaml",
                },
                {
                    "target": {
                        "kind": "ClusterDeployment",
                        "name": "cluster-placeholder",
                    },
                    "path": "patches/clusterdeployment.yaml",
                },
                {
                    "target": {
                        "kind": "MachinePool",
                        "name": "cluster-placeholder-worker",
                    },
                    "path": "patches/machinepool-worker.yaml",
                },
                {
                    "target": {
                        "kind": "ManagedCluster",
                        "name": "cluster-placeholder",
                    },
                    "path": "patches/managedcluster.yaml",
                },
                {
                    "target": {
                        "kind": "KlusterletAddonConfig",
                        "name": "cluster-placeholder",
                    },
                    "path": "patches/klusterletaddonconfig.yaml",
                },
            ],
        },
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/clusterdeployment.yaml"] = yaml.dump(
        [
            {"op": "replace", "path": "/metadata/name", "value": n},
            {"op": "replace", "path": "/metadata/namespace", "value": n},
            {"op": "replace", "path": "/spec/clusterName", "value": n},
            {
                "op": "replace",
                "path": "/spec/platform/aws/region",
                "value": params.region,
            },
            {
                "op": "replace",
                "path": "/spec/provisioning/installConfigSecretRef/name",
                "value": f"{n}-install-config",
            },
            {
                "op": "replace",
                "path": "/spec/provisioning/sshPrivateKeySecretRef/name",
                "value": f"{n}-ssh-key",
            },
            {
                "op": "replace",
                "path": "/spec/provisioning/imageSetRef/name",
                "value": params.image_set,
            },
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    zones = params.zones or get_default_zones(params.region)
    install_config = {
        "apiVersion": "v1",
        "baseDomain": "openshiftpartnerlabs.com",
        "metadata": {"name": n},
        "controlPlane": {
            "name": "master",
            "platform": {
                "aws": {
                    "type": params.control_plane_type,
                    "zones": list(zones),
                }
            },
            "replicas": params.control_plane_replicas,
        },
        "compute": [
            {
                "name": "worker",
                "platform": {
                    "aws": {
                        "rootVolume": {"iops": 4000, "size": 100, "type": "gp3"},
                        "type": params.worker_type,
                        "zones": list(zones),
                    }
                },
                "replicas": params.worker_replicas,
            }
        ],
        "networking": {
            "clusterNetwork": [{"cidr": "10.128.0.0/14", "hostPrefix": 23}],
            "machineNetwork": [{"cidr": "10.0.0.0/16"}],
            "serviceNetwork": ["172.30.0.0/16"],
            "networkType": "OVNKubernetes",
        },
        "platform": {"aws": {"region": params.region}},
        "publish": "External",
    }

    patches["patches/install-config.yaml"] = yaml.dump(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "cluster-placeholder-install-config",
                "namespace": "cluster-placeholder",
            },
            "type": "Opaque",
            "stringData": {
                "install-config.yaml": yaml.dump(
                    install_config, default_flow_style=False, sort_keys=False
                )
            },
        },
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/install-config-meta.yaml"] = yaml.dump(
        [
            {
                "op": "replace",
                "path": "/metadata/name",
                "value": f"{n}-install-config",
            },
            {"op": "replace", "path": "/metadata/namespace", "value": n},
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/namespace.yaml"] = yaml.dump(
        [{"op": "replace", "path": "/metadata/name", "value": n}],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/klusterletaddonconfig.yaml"] = yaml.dump(
        [
            {"op": "replace", "path": "/metadata/name", "value": n},
            {"op": "replace", "path": "/metadata/namespace", "value": n},
            {"op": "replace", "path": "/spec/clusterName", "value": n},
            {"op": "replace", "path": "/spec/clusterNamespace", "value": n},
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/machinepool-worker.yaml"] = yaml.dump(
        [
            {"op": "replace", "path": "/metadata/name", "value": f"{n}-worker"},
            {"op": "replace", "path": "/metadata/namespace", "value": n},
            {"op": "replace", "path": "/spec/clusterDeploymentRef/name", "value": n},
            {
                "op": "replace",
                "path": "/spec/platform/aws/type",
                "value": params.worker_type,
            },
            {
                "op": "replace",
                "path": "/spec/platform/aws/zones",
                "value": list(zones),
            },
            {
                "op": "replace",
                "path": "/spec/replicas",
                "value": params.worker_replicas,
            },
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/managedcluster.yaml"] = yaml.dump(
        [
            {"op": "replace", "path": "/metadata/name", "value": n},
            {"op": "add", "path": "/metadata/labels/name", "value": n},
            {"op": "add", "path": "/metadata/labels/tier", "value": params.tier},
            {
                "op": "add",
                "path": "/metadata/labels/environment",
                "value": params.environment,
            },
            {"op": "add", "path": "/metadata/labels/region", "value": params.region},
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    return patches


def generate_crossplane_patches(params: ClusterParams) -> dict[str, str]:
    n = params.name
    patches: dict[str, str] = {}

    patches["kustomization.yaml"] = yaml.dump(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "namespace": n,
            "resources": ["../../../cluster-templates/aws-ha/base/crossplane"],
            "patches": [
                {
                    "target": {
                        "kind": "User",
                        "name": "cluster-placeholder-ocp-installer",
                    },
                    "path": "patches/user.yaml",
                },
                {
                    "target": {
                        "kind": "Policy",
                        "name": "cluster-placeholder-openshift4installerpolicy",
                    },
                    "path": "patches/policy.yaml",
                },
                {
                    "target": {
                        "kind": "UserPolicyAttachment",
                        "name": "cluster-placeholder-policy-attachment",
                    },
                    "path": "patches/policy-attachment.yaml",
                },
                {
                    "target": {
                        "kind": "AccessKey",
                        "name": "cluster-placeholder-access-key",
                    },
                    "path": "patches/access-key.yaml",
                },
            ],
        },
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/user.yaml"] = yaml.dump(
        [
            {
                "op": "replace",
                "path": "/metadata/name",
                "value": f"{n}-ocp-installer",
            },
            {"op": "replace", "path": "/metadata/namespace", "value": n},
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/policy.yaml"] = yaml.dump(
        [
            {
                "op": "replace",
                "path": "/metadata/name",
                "value": f"{n}-openshift4installerpolicy",
            },
            {"op": "replace", "path": "/metadata/namespace", "value": n},
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/policy-attachment.yaml"] = yaml.dump(
        [
            {
                "op": "replace",
                "path": "/metadata/name",
                "value": f"{n}-policy-attachment",
            },
            {"op": "replace", "path": "/metadata/namespace", "value": n},
            {
                "op": "replace",
                "path": "/spec/forProvider/policyArnRef/name",
                "value": f"{n}-openshift4installerpolicy",
            },
            {
                "op": "replace",
                "path": "/spec/forProvider/userRef/name",
                "value": f"{n}-ocp-installer",
            },
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    patches["patches/access-key.yaml"] = yaml.dump(
        [
            {
                "op": "replace",
                "path": "/metadata/name",
                "value": f"{n}-access-key",
            },
            {"op": "replace", "path": "/metadata/namespace", "value": n},
            {
                "op": "replace",
                "path": "/spec/forProvider/userRef/name",
                "value": f"{n}-ocp-installer",
            },
            {
                "op": "replace",
                "path": "/spec/writeConnectionSecretToRef/namespace",
                "value": n,
            },
        ],
        default_flow_style=False,
        sort_keys=False,
    )

    return patches


def write_cluster_dir(base_path: str, params: ClusterParams) -> str:
    cluster_dir = os.path.join(base_path, params.name)

    top_kustomization = yaml.dump(
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": ["crossplane/", "hive/"],
        },
        default_flow_style=False,
        sort_keys=False,
    )

    hive_patches = generate_hive_patches(params)
    crossplane_patches = generate_crossplane_patches(params)

    _write(os.path.join(cluster_dir, "kustomization.yaml"), top_kustomization)
    for rel_path, content in hive_patches.items():
        _write(os.path.join(cluster_dir, "hive", rel_path), content)
    for rel_path, content in crossplane_patches.items():
        _write(os.path.join(cluster_dir, "crossplane", rel_path), content)

    return cluster_dir


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
