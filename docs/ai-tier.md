# AI tier (`ai`)

This document describes what an operator sets for an `ai` cluster, what the pipelines install, in which order, and the messages of a failed task.

An `ai` cluster is a `base` cluster with Red Hat OpenShift AI. With the accelerator `nvidia-gpu` it also gets the GPU operators and one GPU worker node.

## Inputs

| Input | Set by | Values | Default |
|---|---|---|---|
| Tier | `fleet-scaffold-cluster --tier ai` | `ai` | |
| `ai-accelerator` | `fleet-scaffold-cluster --ai-accelerator`, or `metadata.yaml` | `none`, `nvidia-gpu` | `nvidia-gpu` |
| `openshift-ai-version` | `metadata.yaml` | `v2`, `v3` | `v3` |

[per-cluster-metadata.md](per-cluster-metadata.md#supported-keys) describes both keys.

| `openshift-ai-version` | `ai-accelerator` | Result |
|---|---|---|
| `v3` | `nvidia-gpu` | OpenShift AI 3.x with a DataScienceCluster, the GPU operators and a GPU worker MachinePool |
| `v3` | `none` | OpenShift AI 3.x with a DataScienceCluster, on CPU nodes |
| `v2` | `nvidia-gpu` | The OpenShift AI 2.x operator, the GPU operators and a GPU worker MachinePool |
| `v2` | `none` | The OpenShift AI 2.x operator, on CPU nodes |

## What the pipelines do

| Task | Pipeline | Runs when | Action |
|---|---|---|---|
| `apply-ai-workloads` | `post-provision` | `tier` is `ai` | Checks the catalog of the spoke, then installs the operators of the table below on the spoke in a fixed order |
| `add-ai-workers` | `post-provision` | `tier` is `ai` and `ai-accelerator` is `nvidia-gpu` | Creates the MachinePool `<name>-ai` on the hub and waits for its node |
| `delete-cluster-resources` | `deprovision` | Always | Deletes the MachinePools of the cluster, among them `<name>-ai` |

`apply-ai-workloads` runs after `apply-base-workloads`, and `configure-spoke-rbac` runs after `add-ai-workers`. [architecture.md](architecture.md#post-provision) shows the tasks in the flowchart of `post-provision`.

## Manifests

The manifests are in `workloads/ai/` of this repository:

| Directory | Holds |
|---|---|
| `workloads/ai/common/` | Subscriptions of Serverless and Authorino |
| `workloads/ai/common/v2/` | Subscriptions of Service Mesh 2 and of the OpenShift AI 2.x operator |
| `workloads/ai/common/v3/` | Subscriptions of cert-manager, JobSet, Service Mesh 3 and the OpenShift AI 3.x operator; the JobSet operand; the DataScienceCluster |
| `workloads/ai/gpu/` | Subscriptions of Node Feature Discovery and the NVIDIA GPU Operator; their operands |

The task applies the files one by one with `oc apply -f`. It does not run `kustomize build`.

## Operators

`apply-ai-workloads` requires these packages in the catalog of the spoke and installs them.

| Package | Channel | Catalog | Namespace | Required for |
|---|---|---|---|---|
| `nfd` | `stable` | `redhat-operators` | `openshift-nfd` | `nvidia-gpu` |
| `gpu-operator-certified` | `stable` | `certified-operators` | `nvidia-gpu-operator` | `nvidia-gpu` |
| `serverless-operator` | `stable` | `redhat-operators` | `openshift-serverless` | Every `ai` cluster |
| `authorino-operator` | `stable` | `redhat-operators` | `openshift-operators` | Every `ai` cluster |
| `servicemeshoperator` | `stable` | `redhat-operators` | `openshift-operators` | `v2` |
| `rhods-operator` | `stable` | `redhat-operators` | `redhat-ods-operator` | `v2` |
| `openshift-cert-manager-operator` | `stable-v1` | `redhat-operators` | `cert-manager-operator` | `v3` |
| `job-set` | `stable-v1.0` | `redhat-operators` | `openshift-jobset-operator` | `v3` |
| `servicemeshoperator3` | `stable` | `redhat-operators` | `openshift-operators` | `v3` |
| `rhods-operator` | `stable-3.x` | `redhat-operators` | `redhat-ods-operator` | `v3` |

## Install order

The task stops at the first step that fails.

| Step | For | The task applies | It waits for | Limit |
|---|---|---|---|---|
| 1 | Every `ai` cluster | Nothing | Every required package offers its channel from its catalog, with a current ClusterServiceVersion | None |
| 2 | `nvidia-gpu` | Subscription of `nfd` | ClusterServiceVersion `Succeeded` | 600 s |
| 3 | `nvidia-gpu` | NodeFeatureDiscovery `nfd-instance` | Condition `Available` | 300 s |
| 4 | `nvidia-gpu` | Subscription of `gpu-operator-certified` | ClusterServiceVersion `Succeeded` | 600 s |
| 5 | `nvidia-gpu` | ClusterPolicy `gpu-cluster-policy` | Condition `Ready` | 300 s |
| 6 | Every `ai` cluster | Subscription of `serverless-operator` | ClusterServiceVersion `Succeeded` | 600 s |
| 7 | Every `ai` cluster | Subscription of `authorino-operator` | ClusterServiceVersion `Succeeded` | 600 s |
| 8 | `v2` | Subscription of `servicemeshoperator` | ClusterServiceVersion `Succeeded` | 600 s |
| 8 | `v3` | Subscription of `openshift-cert-manager-operator` | ClusterServiceVersion `Succeeded` | 600 s |
| 9 | `v3` | Subscription of `job-set` | ClusterServiceVersion `Succeeded` | 600 s |
| 10 | `v3` | JobSetOperator `cluster` | Condition `Available` | 300 s |
| 11 | `v3` | Subscription of `servicemeshoperator3` | ClusterServiceVersion `Succeeded` | 600 s |
| 12 | Every `ai` cluster | Subscription of `rhods-operator` | ClusterServiceVersion `Succeeded` | 900 s |
| 13 | `v3` | DataScienceCluster `default-dsc` | Condition `Ready` | 300 s |

Step 1 changes nothing on the spoke. A missing package fails the task before any Subscription is applied.

## GPU workers

`add-ai-workers` runs on the hub. It reads the zones of the existing worker MachinePool and creates a second MachinePool:

| Property | Value |
|---|---|
| Name | `<name>-ai` in the namespace `<name>` |
| Instance type | `g7.4xlarge` |
| Replicas | 1 |
| Root volume | 256 GiB, `gp3`, 4000 IOPS |
| Node labels | `node-role.kubernetes.io/worker`, `node-role.kubernetes.io/ai`, `fleet.openshift.com/tier=ai` |
| Zones | The zones of the existing worker MachinePool; `a`, `b` and `c` of the region when they cannot be read |

The task reads the MachinePool every 30 seconds and waits up to 2400 seconds until the replica is ready.

## Failure messages

| Message | Task | Check on |
|---|---|---|
| `Required operator is unavailable: <reason>` | `apply-ai-workloads` | The spoke: `oc get packagemanifest <package> -n openshift-marketplace`. The reason names the package and what is missing: the package, the catalog, the channel, or a current ClusterServiceVersion. |
| `Timeout waiting for CSV matching '<pattern>' in <namespace>` | `apply-ai-workloads` | The spoke: `oc get csv,subscription.operators.coreos.com,installplan -n <namespace>` |
| `CSV <name> failed to install` | `apply-ai-workloads` | The spoke: `oc describe csv <name> -n <namespace>` |
| `Timeout waiting for <kind>/<name> condition '<condition>'` | `apply-ai-workloads` | The spoke: `oc describe <kind> <name>`; the resources are named in the install order |
| `Condition '<condition>' failed: <reason> - <message>` | `apply-ai-workloads` | The reason and the message of the condition |
| `Failed to apply <file>: <error>` | `apply-ai-workloads` | The error of `oc apply` |
| `Failed to get ClusterDeployment: <error>` | `add-ai-workers` | The hub: `oc get clusterdeployment <name> -n <name>` |
| `Failed to create MachinePool: <error>` | `add-ai-workers` | The error of `oc apply` |
| `MachinePool failed: <message>` | `add-ai-workers` | The hub: `oc describe machinepool <name>-ai -n <name>` |
| `Timeout waiting for MachinePool <name>-ai to be ready` | `add-ai-workers` | The spoke: `oc get machines -n openshift-machine-api` |

After the fix, start `post-provision` again; see the [user guide](user-guide.md#run-a-pipeline-again). Every step applies with `oc apply`, so a second run passes the steps that are already done.

## Limits

- A `v2` cluster gets the OpenShift AI 2.x operator and no DataScienceCluster. `workloads/ai/common/v2/` holds no DataScienceCluster.
- A `post-provision` PipelineRun created by hand without the parameters `openshift-ai-version` and `ai-accelerator` installs `v3` with `nvidia-gpu`, whatever the file says. See [per-cluster-metadata.md](per-cluster-metadata.md#runs-created-by-hand).
- `add-ai-workers` creates one GPU node of one instance type. Neither is a parameter.
- In a `test-vcluster` run with the tier `ai`, both tasks run. `add-ai-workers` reads a ClusterDeployment, which a vCluster does not have. See [vcluster.md](vcluster.md#what-the-test-covers).
