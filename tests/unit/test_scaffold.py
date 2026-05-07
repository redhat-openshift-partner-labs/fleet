import os
import subprocess
from unittest import mock

import pytest
import yaml

from fleet.scaffold import (
    ClusterParams,
    generate_crossplane_patches,
    generate_hive_patches,
    get_default_zones,
    write_cluster_dir,
)


@pytest.fixture()
def params():
    return ClusterParams(
        name="my-cluster",
        region="us-east-2",
        tier="virt",
        environment="development",
        control_plane_type="m7i.4xlarge",
        worker_type="m7i.2xlarge",
        control_plane_replicas=3,
        worker_replicas=3,
        image_set="img4.21.13-x86-64-appsub",
        zones=["us-east-2a", "us-east-2b", "us-east-2c"],
    )


class TestGetDefaultZones:
    def test_us_east_1(self):
        zones = get_default_zones("us-east-1")
        assert zones == ["us-east-1a", "us-east-1b", "us-east-1c"]

    def test_us_east_2(self):
        zones = get_default_zones("us-east-2")
        assert zones == ["us-east-2a", "us-east-2b", "us-east-2c"]

    def test_eu_west_1(self):
        zones = get_default_zones("eu-west-1")
        assert zones == ["eu-west-1a", "eu-west-1b", "eu-west-1c"]


class TestGenerateHivePatches:
    def test_returns_all_expected_files(self, params):
        patches = generate_hive_patches(params)
        expected_files = {
            "kustomization.yaml",
            "patches/clusterdeployment.yaml",
            "patches/install-config.yaml",
            "patches/install-config-meta.yaml",
            "patches/klusterletaddonconfig.yaml",
            "patches/machinepool-worker.yaml",
            "patches/managedcluster.yaml",
            "patches/namespace.yaml",
        }
        assert set(patches.keys()) == expected_files

    def test_kustomization_namespace(self, params):
        patches = generate_hive_patches(params)
        kust = yaml.safe_load(patches["kustomization.yaml"])
        assert kust["namespace"] == "my-cluster"

    def test_clusterdeployment_patch_has_name(self, params):
        patches = generate_hive_patches(params)
        cd = yaml.safe_load(patches["patches/clusterdeployment.yaml"])
        names = [op["value"] for op in cd if op["path"] == "/metadata/name"]
        assert names == ["my-cluster"]

    def test_clusterdeployment_patch_has_region(self, params):
        patches = generate_hive_patches(params)
        cd = yaml.safe_load(patches["patches/clusterdeployment.yaml"])
        regions = [
            op["value"] for op in cd if op["path"] == "/spec/platform/aws/region"
        ]
        assert regions == ["us-east-2"]

    def test_clusterdeployment_patch_has_image_set(self, params):
        patches = generate_hive_patches(params)
        cd = yaml.safe_load(patches["patches/clusterdeployment.yaml"])
        refs = [
            op["value"]
            for op in cd
            if op["path"] == "/spec/provisioning/imageSetRef/name"
        ]
        assert refs == ["img4.21.13-x86-64-appsub"]

    def test_install_config_has_correct_name(self, params):
        patches = generate_hive_patches(params)
        ic_raw = patches["patches/install-config.yaml"]
        ic = yaml.safe_load(ic_raw)
        embedded = yaml.safe_load(ic["stringData"]["install-config.yaml"])
        assert embedded["metadata"]["name"] == "my-cluster"

    def test_install_config_has_correct_region(self, params):
        patches = generate_hive_patches(params)
        ic = yaml.safe_load(patches["patches/install-config.yaml"])
        embedded = yaml.safe_load(ic["stringData"]["install-config.yaml"])
        assert embedded["platform"]["aws"]["region"] == "us-east-2"

    def test_install_config_zones_match_region(self, params):
        patches = generate_hive_patches(params)
        ic = yaml.safe_load(patches["patches/install-config.yaml"])
        embedded = yaml.safe_load(ic["stringData"]["install-config.yaml"])
        cp_zones = embedded["controlPlane"]["platform"]["aws"]["zones"]
        w_zones = embedded["compute"][0]["platform"]["aws"]["zones"]
        assert cp_zones == ["us-east-2a", "us-east-2b", "us-east-2c"]
        assert w_zones == ["us-east-2a", "us-east-2b", "us-east-2c"]

    def test_install_config_meta_patch(self, params):
        patches = generate_hive_patches(params)
        meta = yaml.safe_load(patches["patches/install-config-meta.yaml"])
        names = [op["value"] for op in meta if op["path"] == "/metadata/name"]
        assert names == ["my-cluster-install-config"]

    def test_managedcluster_has_tier_label(self, params):
        patches = generate_hive_patches(params)
        mc = yaml.safe_load(patches["patches/managedcluster.yaml"])
        tier_ops = [op for op in mc if op["path"] == "/metadata/labels/tier"]
        assert tier_ops[0]["value"] == "virt"

    def test_managedcluster_has_environment_label(self, params):
        patches = generate_hive_patches(params)
        mc = yaml.safe_load(patches["patches/managedcluster.yaml"])
        env_ops = [op for op in mc if op["path"] == "/metadata/labels/environment"]
        assert env_ops[0]["value"] == "development"

    def test_managedcluster_has_name_label(self, params):
        patches = generate_hive_patches(params)
        mc = yaml.safe_load(patches["patches/managedcluster.yaml"])
        name_ops = [op for op in mc if op["path"] == "/metadata/labels/name"]
        assert len(name_ops) == 1
        assert name_ops[0]["value"] == "my-cluster"

    def test_managedcluster_has_region_label(self, params):
        patches = generate_hive_patches(params)
        mc = yaml.safe_load(patches["patches/managedcluster.yaml"])
        region_ops = [op for op in mc if op["path"] == "/metadata/labels/region"]
        assert len(region_ops) == 1
        assert region_ops[0]["value"] == "us-east-2"

    def test_machinepool_has_worker_type(self, params):
        patches = generate_hive_patches(params)
        mp = yaml.safe_load(patches["patches/machinepool-worker.yaml"])
        type_ops = [op for op in mp if op["path"] == "/spec/platform/aws/type"]
        assert type_ops[0]["value"] == "m7i.2xlarge"

    def test_namespace_patch(self, params):
        patches = generate_hive_patches(params)
        ns = yaml.safe_load(patches["patches/namespace.yaml"])
        assert ns[0]["value"] == "my-cluster"


class TestGenerateCrossplanePatches:
    def test_returns_all_expected_files(self, params):
        patches = generate_crossplane_patches(params)
        expected_files = {
            "kustomization.yaml",
            "patches/user.yaml",
            "patches/policy.yaml",
            "patches/policy-attachment.yaml",
            "patches/access-key.yaml",
        }
        assert set(patches.keys()) == expected_files

    def test_user_patch_has_name(self, params):
        patches = generate_crossplane_patches(params)
        user = yaml.safe_load(patches["patches/user.yaml"])
        assert user[0]["value"] == "my-cluster-ocp-installer"

    def test_policy_patch_has_name(self, params):
        patches = generate_crossplane_patches(params)
        policy = yaml.safe_load(patches["patches/policy.yaml"])
        meta_name = [op for op in policy if op["path"] == "/metadata/name"]
        assert meta_name[0]["value"] == "my-cluster-openshift4installerpolicy"

    def test_kustomization_namespace(self, params):
        patches = generate_crossplane_patches(params)
        kust = yaml.safe_load(patches["kustomization.yaml"])
        assert kust["namespace"] == "my-cluster"

    def test_user_patch_has_namespace(self, params):
        patches = generate_crossplane_patches(params)
        user = yaml.safe_load(patches["patches/user.yaml"])
        ns_ops = [op for op in user if op["path"] == "/metadata/namespace"]
        assert len(ns_ops) == 1
        assert ns_ops[0]["value"] == "my-cluster"

    def test_policy_patch_has_namespace(self, params):
        patches = generate_crossplane_patches(params)
        policy = yaml.safe_load(patches["patches/policy.yaml"])
        ns_ops = [op for op in policy if op["path"] == "/metadata/namespace"]
        assert len(ns_ops) == 1
        assert ns_ops[0]["value"] == "my-cluster"

    def test_policy_attachment_patch_has_namespace(self, params):
        patches = generate_crossplane_patches(params)
        pa = yaml.safe_load(patches["patches/policy-attachment.yaml"])
        ns_ops = [op for op in pa if op["path"] == "/metadata/namespace"]
        assert len(ns_ops) == 1
        assert ns_ops[0]["value"] == "my-cluster"

    def test_access_key_patch_has_namespace(self, params):
        patches = generate_crossplane_patches(params)
        ak = yaml.safe_load(patches["patches/access-key.yaml"])
        ns_ops = [op for op in ak if op["path"] == "/metadata/namespace"]
        assert len(ns_ops) == 1
        assert ns_ops[0]["value"] == "my-cluster"

    def test_access_key_namespace(self, params):
        patches = generate_crossplane_patches(params)
        ak = yaml.safe_load(patches["patches/access-key.yaml"])
        ns_ops = [
            op
            for op in ak
            if op["path"] == "/spec/writeConnectionSecretToRef/namespace"
        ]
        assert ns_ops[0]["value"] == "my-cluster"


class TestWriteClusterDir:
    def test_creates_all_files(self, params, tmp_path):
        write_cluster_dir(str(tmp_path), params)
        cluster_dir = tmp_path / "my-cluster"
        assert (cluster_dir / "kustomization.yaml").exists()
        assert (cluster_dir / "hive" / "kustomization.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "clusterdeployment.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "install-config.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "install-config-meta.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "namespace.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "machinepool-worker.yaml").exists()
        assert (cluster_dir / "hive" / "patches" / "managedcluster.yaml").exists()
        assert (
            cluster_dir / "hive" / "patches" / "klusterletaddonconfig.yaml"
        ).exists()
        assert (cluster_dir / "crossplane" / "kustomization.yaml").exists()
        assert (cluster_dir / "crossplane" / "patches" / "user.yaml").exists()
        assert (cluster_dir / "crossplane" / "patches" / "policy.yaml").exists()
        assert (
            cluster_dir / "crossplane" / "patches" / "policy-attachment.yaml"
        ).exists()
        assert (cluster_dir / "crossplane" / "patches" / "access-key.yaml").exists()

    def test_top_level_kustomization(self, params, tmp_path):
        write_cluster_dir(str(tmp_path), params)
        kust = yaml.safe_load(
            (tmp_path / "my-cluster" / "kustomization.yaml").read_text()
        )
        assert "crossplane/" in kust["resources"]
        assert "hive/" in kust["resources"]
