# Cluster Overlays

Each subdirectory defines a cluster as a kustomize overlay on the `aws-ha` base template. Multiple files reference the same values (region, cluster name, instance types), and they **must stay in sync** — changing a value in one file but not the others causes install failures.

## Directory Structure

```
clusters/<cluster-name>/
├── kustomization.yaml                        # References crossplane/ and hive/
├── .deprovision                              # Marker file — presence triggers deprovision pipeline
├── crossplane/
│   ├── kustomization.yaml                    # target+path refs only
│   └── patches/
│       ├── user.yaml                         # IAM user name
│       ├── policy.yaml                       # IAM policy name
│       ├── policy-attachment.yaml            # Policy-to-user attachment refs
│       └── access-key.yaml                   # Access key refs and credential namespace
└── hive/
    ├── kustomization.yaml                    # target+path refs only
    └── patches/
        ├── install-config.yaml               # Full install-config (strategic merge)
        ├── install-config-meta.yaml           # Secret metadata (name, namespace)
        ├── namespace.yaml                    # Namespace name
        ├── clusterdeployment.yaml            # Name, namespace, region, secret refs
        ├── machinepool-worker.yaml           # Name, namespace, type, zones, replicas
        ├── managedcluster.yaml               # Name, tier/environment labels
        └── klusterletaddonconfig.yaml        # Name, namespace, cluster refs
```

**Base template:** `cluster-templates/aws-ha/base/`

All patches are in separate files under `patches/`. The `kustomization.yaml` files contain only `target:` + `path:` references — no inline patch blocks.

| Directory | Patch files | Purpose |
|-----------|------------|---------|
| `crossplane/patches/` | `user.yaml`, `policy.yaml`, `policy-attachment.yaml`, `access-key.yaml` | IAM resource names and cross-references |
| `hive/patches/` | `install-config.yaml` (strategic merge) | Full install-config with infra settings |
| `hive/patches/` | All others (JSON patch) | Resource names, namespace, region, labels, secret refs |

## Creating a New Cluster

Copy an existing overlay and replace every occurrence of the old cluster name. The `379b5094-ibmvirt` overlay is a good reference since it patches the region (us-east-2).

### Checklist

1. Create `clusters/<name>/kustomization.yaml` — reference `crossplane/` and `hive/`
2. Create `clusters/<name>/crossplane/kustomization.yaml` — replace all `cluster-placeholder` names
3. Create `clusters/<name>/hive/kustomization.yaml` — replace all `cluster-placeholder` names + set region and tier
4. Create `clusters/<name>/hive/patches/install-config.yaml` — set instance types, replicas, zones, region
5. Validate: `kustomize build clusters/<name>`

## Common Changes

### Cluster Name

Every file patches the base placeholder `cluster-placeholder` to the actual cluster name. The name appears in metadata, spec references, and cross-resource refs. All must match.

| File | Fields to patch |
|------|----------------|
| `hive/kustomization.yaml` | Namespace `/metadata/name`, ClusterDeployment `/metadata/name` + `/metadata/namespace` + `/spec/clusterName`, MachinePool `/metadata/name` + `/metadata/namespace` + `/spec/clusterDeploymentRef/name`, ManagedCluster `/metadata/name`, KlusterletAddonConfig `/metadata/name` + `/metadata/namespace` + `/spec/clusterName` + `/spec/clusterNamespace`, Secret `/metadata/name` + `/metadata/namespace` |
| `hive/kustomization.yaml` | ClusterDeployment `/spec/provisioning/installConfigSecretRef/name` (must be `<name>-install-config`), `/spec/provisioning/sshPrivateKeySecretRef/name` (must be `<name>-ssh-key`) |
| `hive/patches/install-config.yaml` | `metadata.name` inside the embedded install-config YAML |
| `crossplane/kustomization.yaml` | User `/metadata/name` (`<name>-ocp-installer`), Policy `/metadata/name` + `/spec/forProvider/name`, UserPolicyAttachment `/metadata/name` + `/spec/forProvider/policyArnRef/name` + `/spec/forProvider/userRef/name`, AccessKey `/metadata/name` + `/spec/forProvider/userRef/name` + `/spec/writeConnectionSecretToRef/namespace` |

### Region and Availability Zones

Region appears in **three places** that must agree. Zones must be valid for the chosen region.

| File | Field | Base default |
|------|-------|-------------|
| `hive/kustomization.yaml` | ClusterDeployment `/spec/platform/aws/region` | `us-east-1` |
| `hive/patches/install-config.yaml` | `platform.aws.region` | `us-east-1` |
| `hive/patches/install-config.yaml` | `controlPlane.platform.aws.zones[]` | `us-east-1a, 1b, 1c` |
| `hive/patches/install-config.yaml` | `compute[0].platform.aws.zones[]` | `us-east-1a, 1b, 1c` |

If you change the base region (us-east-1), you must update **all four**. The ClusterDeployment region and install-config region must match, and the zones must belong to that region.

### Instance Types

Instance types are set **independently** for masters, workers (install-config), and the MachinePool. They do not auto-sync.

| Component | File | Field | Base default |
|-----------|------|-------|-------------|
| Masters | `hive/patches/install-config.yaml` | `controlPlane.platform.aws.type` | `m8i.2xlarge` |
| Workers (install-config) | `hive/patches/install-config.yaml` | `compute[0].platform.aws.type` | `m8i.2xlarge` |
| Workers (MachinePool) | base `machinepool-worker.yaml` | `/spec/platform/aws/type` | `m5.2xlarge` |

The MachinePool governs day-2 scaling. If it specifies a different instance type than the install-config, new nodes added after install will use the MachinePool type.

To override the MachinePool instance type, add a patch in `hive/kustomization.yaml`:

```yaml
- target:
    kind: MachinePool
    name: cluster-placeholder-worker
  patch: |
    - op: replace
      path: /spec/platform/aws/type
      value: m7i.4xlarge
```

### Node Count (Replicas)

Replicas are set in the install-config and independently in the MachinePool.

| Component | File | Field | Base default |
|-----------|------|-------|-------------|
| Masters | `hive/patches/install-config.yaml` | `controlPlane.replicas` | `3` |
| Workers (install-config) | `hive/patches/install-config.yaml` | `compute[0].replicas` | `3` |
| Workers (MachinePool) | base `machinepool-worker.yaml` | `/spec/replicas` | `3` |

For SNO (single-node OpenShift): set `controlPlane.replicas: 1` and `compute[0].replicas: 0`.

### Tier Label

Set on ManagedCluster in `hive/kustomization.yaml`. Determines which day-2 workloads ArgoCD applies.

```yaml
- target:
    kind: ManagedCluster
    name: cluster-placeholder
  patch: |
    - op: add
      path: /metadata/labels/tier
      value: base    # base | virt | ai
```

## Coordination Requirements

Fields that must match across files:

| Value | Must match in |
|-------|--------------|
| Cluster name | Namespace name, ClusterDeployment name/namespace/clusterName, MachinePool name/namespace/clusterDeploymentRef, ManagedCluster name, KlusterletAddonConfig name/namespace/clusterName/clusterNamespace, Secret name/namespace, all Crossplane resource names/namespace, install-config `metadata.name` |
| Region | ClusterDeployment `spec.platform.aws.region`, install-config `platform.aws.region` |
| Zones | install-config `controlPlane.platform.aws.zones[]`, install-config `compute[0].platform.aws.zones[]` — must be valid for the region |
| Install-config secret name | ClusterDeployment `spec.provisioning.installConfigSecretRef.name`, Secret `metadata.name` — must be `<cluster-name>-install-config` |
| IAM user name | User `metadata.name`, UserPolicyAttachment `spec.forProvider.userRef.name`, AccessKey `spec.forProvider.userRef.name` |
| IAM policy name | Policy `metadata.name`, UserPolicyAttachment `spec.forProvider.policyArnRef.name` |
| Credential namespace | AccessKey `spec.writeConnectionSecretToRef.namespace` — must match cluster namespace |

## Common Failures

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `Zone us-east-1a does not exist in region us-east-2` | Region changed in install-config but zones still reference old region | Update `controlPlane.platform.aws.zones[]` and `compute[0].platform.aws.zones[]` to match new region |
| ClusterDeployment stuck provisioning | `installConfigSecretRef.name` in ClusterDeployment doesn't match Secret `metadata.name` | Ensure both use `<cluster-name>-install-config` |
| ClusterDeployment stuck provisioning | Region in ClusterDeployment doesn't match region in install-config | Set `/spec/platform/aws/region` in the ClusterDeployment patch to match `platform.aws.region` in install-config |
| AWS credentials not found | AccessKey `writeConnectionSecretToRef.namespace` doesn't match cluster namespace | Set namespace on AccessKey to cluster name |
| MachinePool not joining cluster | `clusterDeploymentRef.name` doesn't match ClusterDeployment name | Patch MachinePool `/spec/clusterDeploymentRef/name` to cluster name |
| New worker nodes have wrong instance type | MachinePool `spec.platform.aws.type` differs from install-config `compute[0].platform.aws.type` | Patch MachinePool type to match desired worker type, or accept the divergence intentionally |
| IAM policy not attached | Policy `metadata.name` doesn't match UserPolicyAttachment `policyArnRef.name` | Ensure both use `<cluster-name>-openshift4installerpolicy` |

## Base Template Defaults

For reference, the base template at `cluster-templates/aws-ha/base/` provides:

| Setting | Default |
|---------|---------|
| Base domain | `openshiftpartnerlabs.com` |
| Region | `us-east-1` |
| Zones | `us-east-1a`, `us-east-1b`, `us-east-1c` |
| Master instance type | `m8i.2xlarge` |
| Master replicas | `3` |
| Worker instance type (install-config) | `m8i.2xlarge` |
| Worker instance type (MachinePool) | `m5.2xlarge` |
| Worker replicas | `3` |
| Worker root volume | `100 GB gp3, 4000 IOPS` |
| Network type | `OVNKubernetes` |
| Cluster network | `10.128.0.0/14` (`/23` host prefix) |
| Service network | `172.30.0.0/16` |
| Machine network | `10.0.0.0/16` |
| Image set | `img4.20.10-x86-64-appsub` |
| Environment label | `production` |
