# User Guide

Operator-facing guide for provisioning, managing, and deprovisioning OpenShift clusters through the fleet control plane. For architecture rationale and design decisions, see [architecture.md](architecture.md).

## Prerequisites

Before operating the fleet control plane you need:

- **Hub cluster access** — `oc` CLI authenticated against the hub with cluster-admin privileges
- **Tekton CLI** — `tkn` installed ([docs](https://tekton.dev/docs/cli/))
- **Git access** — push access to this repository
- **Hub-side secrets populated:**
  - quay.io pull secret for the pipeline image (see [image-pull-secret-setup.md](image-pull-secret-setup.md))
  - Crossplane AWS provider credentials (pre-installed)
  - Keycloak admin credentials (Secret referenced by post-provision pipeline)
  - cert-manager ClusterIssuer configured for your DNS zone

## Provisioning a Cluster

Provisioning is triggered by committing a new cluster directory to the [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) repository under `provision/`.

### 1. Create the cluster directory

In the fleet-clusters repo, create a new cluster directory under `provision/`:

```bash
cd fleet-clusters
cp -r provision/<existing-cluster> provision/<cluster-name>
```

### 2. Customize the kustomization

Edit `provision/<cluster-name>/kustomization.yaml` and replace every occurrence of the placeholder name with your cluster name. The key fields to set:

| Field | Location | Description |
|-------|----------|-------------|
| `namespace` | Top-level | Cluster namespace on the hub |
| Cluster name | All patches | Must match across ClusterDeployment, ManagedCluster, MachinePool, etc. |
| `tier` label | ManagedCluster patch | `base`, `virt`, or `ai` — controls post-provision workloads |
| `environment` label | ManagedCluster patch | e.g. `development`, `production` |

### 3. Customize install config (optional)

Edit `provision/<cluster-name>/patches/install-config.yaml` to override:

- AWS region
- Compute node instance type or count
- Network CIDR ranges
- Any other install-config fields

### 4. Add per-cluster metadata (optional)

Create `provision/<cluster-name>/metadata.yaml` for per-cluster configuration. See [per-cluster-metadata.md](per-cluster-metadata.md) for details.

### 5. Commit and push

```bash
git checkout -b feat/add-<cluster-name>
git add provision/<cluster-name>/
git commit -S -s -m "feat(clusters): add <cluster-name>"
git push origin feat/add-<cluster-name>
```

Once the commit lands on `main` (via PR merge), the EventListener detects the new `provision/**` path and triggers the **pre-provision pipeline**.

### What the provision pipeline does

The pipeline runs these tasks in sequence:

1. **git-clone** — checks out the repo at the triggering commit
2. **create-cluster-namespace** — creates the cluster namespace on the hub
3. **create-ssh-key** — generates an SSH keypair and stores it as a Secret
4. **create-pull-secret** — copies the global pull secret into the cluster namespace
5. **apply-crossplane-credentials** — applies Crossplane CRs for per-cluster IAM user
6. **wait-for-aws-credentials** — waits for Crossplane to provision the IAM access key
7. **transform-aws-credentials** — converts Crossplane credentials into the format Hive expects
8. **validate-cluster-inputs** — validates all required resources exist before provisioning
9. **apply-cluster-crs** — applies the Kustomize-rendered ClusterDeployment, ManagedCluster, etc.
10. **wait-for-hive-ready** — waits for Hive to report the cluster as installed
11. **wait-for-managed-cluster** — waits for ACM to report the cluster as joined and available
12. **extract-spoke-kubeconfig** — extracts the spoke kubeconfig from the hub
13. **read-cluster-metadata** — reads per-cluster values from `metadata.yaml` (see [per-cluster-metadata.md](per-cluster-metadata.md))
14. **read-cluster-tier** — reads the tier label from the ManagedCluster
15. **label-for-post-provision** — labels the cluster to signal readiness
16. **trigger-post-provision** — triggers the post-provision pipeline (forwards tier and metadata values)

## Cluster Tiers

The `tier` label on the ManagedCluster determines what software is deployed post-provision:

| Tier | Description |
|------|-------------|
| `base` | Core configuration only — OAuth, SSL, RBAC, base workloads |
| `virt` | Base + OpenShift Virtualization; optional NFD when its catalog package is available |
| `ai` | Base + OpenShift AI; required operators are preflighted for the selected version and accelerator |

For `tier=ai`, set `ai-accelerator` in `metadata.yaml`:

| `ai-accelerator` | Result |
|---|---|
| `none` | CPU-only OpenShift AI; no NFD, NVIDIA GPU Operator, GPU ClusterPolicy, or AI worker MachinePool |
| `nvidia-gpu` | GPU-backed OpenShift AI; installs NFD, NVIDIA GPU Operator, GPU ClusterPolicy, and an AI worker MachinePool |

`ai-accelerator` defaults to `nvidia-gpu` and is ignored for `base` and `virt`.

Before applying AI operator subscriptions, the pipeline checks the spoke's `PackageManifest` resources for the exact v2/v3 and CPU/GPU stack. A missing required operator fails the task before partial installation. For `tier=virt`, OpenShift Virtualization is required and NFD is optional; if NFD is unavailable or fails to install, the virtualization task continues.

## Post-Provision

The post-provision pipeline runs automatically after a successful provision. It configures the spoke cluster for partner access:

1. **git-clone** — checks out the repo
2. **extract-spoke-kubeconfig** — retrieves spoke credentials from the hub
3. **save-spoke-kubeconfig** — persists kubeconfig to the workspace
4. **create-cluster-cronjob** — creates the recurring cluster job in the hub `default` namespace
5. **register-keycloak-client** — registers an OIDC client in Keycloak for the spoke
6. **configure-spoke-oauth** — configures OpenShift OAuth on the spoke to use Keycloak
7. **request-ssl-cert** — requests a TLS certificate via cert-manager on the hub
8. **wait-for-ssl-ready** — waits for the certificate to be issued
9. **extract-cert-material** — extracts the signed cert and key
10. **apply-base-workloads** — applies tier-specific day-2 workloads to the spoke
11. **configure-spoke-rbac** — sets up RBAC for partner access on the spoke
12. **create-access-paste** — creates a password-protected PrivateBin paste containing the console URL, kubeadmin password, and kubeconfig
13. **finalize-spoke** — deletes leftover installer pods and the kubeadmin secret to prepare the cluster for handoff

The access paste URL and password are stored in the `openshift-pipelines`
namespace as `<cluster-name>-access-paste`:

```bash
oc get secret <cluster-name>-access-paste -n openshift-pipelines \
  -o jsonpath='{.data.url}' | base64 -d
oc get secret <cluster-name>-access-paste -n openshift-pipelines \
  -o jsonpath='{.data.password}' | base64 -d
```

The paste expires after one week by default. Set `privatebin-expire` in
`fleet-pipeline-config` to change the retention period.

## Monitoring Pipeline Runs

### Using the Tekton CLI

```bash
# List recent PipelineRuns
tkn pipelinerun list -n openshift-pipelines

# Watch a running pipeline
tkn pipelinerun logs <pipelinerun-name> -n openshift-pipelines -f

# Check status
tkn pipelinerun describe <pipelinerun-name> -n openshift-pipelines
```

### Using the OpenShift Console

Navigate to **Pipelines → PipelineRuns** in the `openshift-pipelines` namespace. The console shows task status, logs, and duration for each step.

## Deprovisioning a Cluster

Deprovisioning is triggered by pushing a sentinel file to the [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) repository under `deprovision/`.

### 1. Create the deprovision sentinel

In the fleet-clusters repo:

```bash
git checkout -b feat/remove-<cluster-name>
touch deprovision/<cluster-name>-archive
git add deprovision/<cluster-name>-archive
git commit -S -s -m "feat(clusters): deprovision <cluster-name>"
git push origin feat/remove-<cluster-name>
```

Once merged to `main`, the EventListener detects the new `deprovision/**` path and triggers the **deprovision pipeline**. After successful deprovision, the archive workflow in fleet-clusters moves the cluster from `provision/` to `archive/`.

### What the deprovision pipeline does

1. **delete-cluster-resources** — deletes ClusterDeployment, ManagedCluster, and related CRs
2. **wait-hive-uninstall** — waits for Hive to finish destroying the cloud infrastructure
3. **cleanup-hub-artifacts** — removes the cluster namespace, secrets, recurring hub job, and leftover resources from the hub
4. **verify-deprovision** — confirms all resources have been cleaned up

## Troubleshooting

### Pipeline fails at wait-for-aws-credentials

Crossplane may not have provisioned the IAM user yet. Check:

```bash
oc get user.iam.aws.crossplane.io -n <cluster-name>
oc get accesskey.iam.aws.crossplane.io -n <cluster-name>
```

Verify the Crossplane AWS provider is healthy:

```bash
oc get provider.pkg.crossplane.io
```

### Pipeline fails at wait-for-hive-ready

The cluster install is taking too long or has failed. Check the Hive install log:

```bash
oc get clusterdeployment <cluster-name> -n <cluster-name> -o yaml | grep -A5 conditions
oc logs -l hive.openshift.io/cluster-deployment-name=<cluster-name> -n <cluster-name> --tail=100
```

### Pipeline fails at wait-for-managed-cluster

ACM has not imported the cluster. Verify:

```bash
oc get managedcluster <cluster-name> -o yaml | grep -A10 conditions
```

### Post-provision OAuth or SSL failures

Check that Keycloak is reachable from the hub and the admin secret exists:

```bash
oc get secret <keycloak-admin-secret> -n openshift-pipelines
```

For SSL, verify cert-manager ClusterIssuer health:

```bash
oc get clusterissuer -o yaml | grep -A5 conditions
```

### Checking task logs for a specific step

```bash
tkn taskrun logs <taskrun-name> -n openshift-pipelines
```

Or find the TaskRun name from the PipelineRun:

```bash
tkn pipelinerun describe <pipelinerun-name> -n openshift-pipelines
```

## Related Documentation

- [Architecture and design rationale](architecture.md)
- [Per-cluster metadata](per-cluster-metadata.md)
- [Image pull secret setup](image-pull-secret-setup.md)
- [Pipeline sequence diagrams](diagrams/)
