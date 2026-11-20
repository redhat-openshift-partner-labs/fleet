# vCluster Test

This document describes how the `test-vcluster` pipeline tests `post-provision` against a temporary vCluster on the hub, and what the test covers.

A vCluster is a Kubernetes cluster that runs as pods in one namespace of the hub. The test needs no cloud resources. `<name>` is the cluster name of the test.

## What the test covers

`run-post-provision` starts `post-provision` with `openshift-cluster=false`. Ten tasks need an OpenShift cluster and are skipped:

| Task | Not tested |
|---|---|
| `register-keycloak-client` | The OIDC client in Keycloak |
| `configure-spoke-oauth` | OAuth on the spoke |
| `create-cluster-issuer` | The ClusterIssuer of the cluster |
| `request-ssl-cert` | The Certificate |
| `wait-for-ssl-ready` | The wait for the Certificate |
| `extract-cert-material` | The leaf Secret |
| `configure-spoke-default-cert` | The default ingress certificate |
| `configure-spoke-rbac` | The group `cluster-admins` |
| `create-access-paste` | The access paste |
| `finalize-spoke` | The removal of installer pods and of the kubeadmin Secret |

The other tasks run as for a real cluster; [architecture.md](architecture.md#post-provision) lists them.

- `load-config`, `git-clone`, `extract-spoke-kubeconfig`, `save-spoke-kubeconfig`, `create-cluster-cronjob` and `apply-base-workloads` run for every tier.
- The tasks of the tier run for `virt`, `ai` and `coco`.
- The run receives no value of `metadata.yaml`. It uses the defaults of the pipeline parameters.

## Run the test

The pipeline has nine parameters and the workspace `shared-workspace`.

| Parameter | Default | Effect |
|---|---|---|
| `cluster-name` | Required | Name of the vCluster, of the namespace for the hub resources, and of the ManagedCluster |
| `namespace` | Required | Namespace of the hub in which the vCluster runs |
| `tier` | `base` | Tier label of the ManagedCluster and tier of the `post-provision` run |
| `pipeline-image` | `quay.io/rhopl/fleet-pipeline:latest` | Image of the task steps. `delete-test-vcluster` uses the parameter; the other tasks use the result of `load-config`. |
| `values-file` | Empty | Path of a vCluster values file in the workspace. It replaces the generated values. |
| `extra-sans` | Empty | Names to add to the certificate of the vCluster API, separated by spaces |
| `route-san` | Empty | Host name of a passthrough Route to the vCluster API. The kubeconfig then uses `https://<route-san>:443`. |
| `create-aws-creds` | `false` | `true` creates a placeholder Secret `aws-credentials` |
| `timeout` | `600` | Seconds to wait for the `post-provision` run |

> **To be verified:** the command that starts the pipeline. This section will hold it once it is confirmed on a hub.

No task writes to the workspace before `create-test-vcluster`, so a `values-file` must already be on the volume that the run gets.

## The pipeline

![test-vcluster task flowchart](diagrams/test-vcluster-flow.svg)

Diagram source: [diagrams/test-vcluster-flow.mermaid](diagrams/test-vcluster-flow.mermaid)

| Task | Tool | Action |
|---|---|---|
| `load-config` | Task `config-loader` | Reads the ConfigMap `fleet-pipeline-config`. The later tasks use its result `pipeline-image`. |
| `create-test-vcluster` | `fleet-create-test-vcluster` | Checks the name, then runs `vcluster create <name> -n <namespace> --connect=false`, waits 30 seconds, reads the kubeconfig from the Secret `vc-<name>`, and writes it to the file `kubeconfig` of the workspace |
| `seed-test-vcluster` | `fleet-seed-test-vcluster` | Checks the name, then creates the hub resources that `post-provision` expects of a cluster; see [Hub resources](#hub-resources) |
| `run-post-provision` | `fleet-run-post-provision` | Creates the PipelineRun of `post-provision` and reads its state every 30 seconds until it succeeds, fails, or the timeout passes |
| `delete-test-vcluster` | `fleet-delete-test-vcluster` | Checks the name, then deletes the resources of the test; see [Cleanup](#cleanup) |

![test-vcluster sequence diagram](diagrams/test-vcluster-sequence.svg)

Diagram source: [diagrams/test-vcluster-sequence.mermaid](diagrams/test-vcluster-sequence.mermaid)

The first four tasks run in order, and a failed task stops them. `delete-test-vcluster` is the `finally` task of the pipeline: it runs after the fourth task, and after a failed task.

## Name check

The tools create and delete hub resources by the name of the test. `create-test-vcluster`, `seed-test-vcluster` and `delete-test-vcluster` exit with 1, before they change anything, in these cases:

| Case | Message |
|---|---|
| A ClusterDeployment `<name>` exists in the namespace `<name>` | `ClusterDeployment <name> exists in namespace <name>` |
| The ManagedCluster `<name>` exists without the label `cloud=vcluster` | `ManagedCluster <name> does not carry the label cloud=vcluster` |
| The hub does not answer the read of one of the two | `cannot read <kind> <name>: <error>` |

`seed-test-vcluster` sets the label `fleet-test-vcluster=<name>` on the namespace `<name>`. It exits with 1 when the namespace exists without the label and holds no Secret `vc-<name>`: the namespace existed before the test. `delete-test-vcluster` deletes the namespace `<name>` only with the label.

## Cleanup

`delete-test-vcluster` does this in order. It attempts every step, and exits with 1 at the end when a deletion failed. Each failure is a log line `Not deleted: <kind> <name>: <error>`.

1. Deletes the ManagedCluster `<name>` and waits up to 300 seconds for it to be gone.
2. When the namespace of the vCluster exists: deletes the Route `<name>` and runs `vcluster delete <name> -n <namespace>`. When that fails and the Secret `vc-<name>` exists, it deletes the namespace of the vCluster. Without the Secret it keeps the namespace: no vCluster of that name runs in it.
3. Deletes the namespace `<name>` when it carries the label `fleet-test-vcluster=<name>`, and waits up to 300 seconds. Without the label it logs a warning and keeps the namespace.
4. Deletes the CronJob `<name>` in `default`.
5. Deletes the Secret `<name>-spoke-kubeconfig` in `openshift-pipelines`.

Tekton does not run the task in two cases:

- The run is cancelled. Tekton runs the `finally` task of a cancelled run only for `spec.status: CancelledRunFinally`.
- The run reaches its timeout, `spec.timeouts.pipeline`, 1 hour unless the hub sets another default. The timeout covers the `finally` task. A run whose parameter `timeout` is close to it needs `spec.timeouts` with `tasks` and `finally`, whose sum is at most `pipeline`.

## Hub resources

| Resource | Namespace | Created by | Deleted by |
|---|---|---|---|
| The vCluster `<name>` with its Secret `vc-<name>` | The parameter `namespace` | `create-test-vcluster` | `delete-test-vcluster` |
| Route `<name>`, only with `route-san` | The parameter `namespace` | `create-test-vcluster` | `delete-test-vcluster` |
| Namespace `<name>` with the label `fleet-test-vcluster=<name>` | | `seed-test-vcluster` | `delete-test-vcluster` |
| Secret `<name>-admin-kubeconfig` | `<name>` | `seed-test-vcluster` | `delete-test-vcluster`, with the namespace |
| Secret `auto-import-secret` | `<name>` | `seed-test-vcluster` | `delete-test-vcluster`, with the namespace |
| Secret `aws-credentials`, only with `create-aws-creds` | `<name>` | `seed-test-vcluster` | `delete-test-vcluster`, with the namespace |
| ManagedCluster `<name>` with the labels `tier`, `cloud=vcluster` and `vendor=Kubernetes` | | `seed-test-vcluster` | `delete-test-vcluster` |
| PipelineRun `post-provision-<name>-*` | `openshift-pipelines` | `run-post-provision` | No task |
| CronJob `<name>` | `default` | `create-cluster-cronjob` of `post-provision` | `delete-test-vcluster` |
| Secret `<name>-spoke-kubeconfig` | `openshift-pipelines` | `save-spoke-kubeconfig` of `post-provision` | `delete-test-vcluster` |

`post-provision` finds the kubeconfig through its parameter `spoke-kubeconfig`, which `run-post-provision` sets to `<name>-admin-kubeconfig`. For a real cluster the parameter is empty and the task reads the Secret that the ClusterDeployment names.

Without `values-file`, `create-test-vcluster` generates the values of the vCluster: the SANs of the API certificate, and two RoleBindings in the namespace that bind the ServiceAccounts `vc-<name>` and `vc-workload-<name>` to the ClusterRole `cluster-admin`.

## After a run

Every run leaves the PipelineRun `post-provision-<name>-*`; its log is the result of the test. Delete it when it is no longer needed:

```bash
tkn pipelinerun delete <post-provision-pipelinerun> -n openshift-pipelines
```

When `delete-test-vcluster` failed or did not run, check that `<name>` is the name of the test and of no real cluster, then remove what remains:

```bash
oc delete managedcluster <name> --ignore-not-found
oc delete route <name> -n <namespace> --ignore-not-found
vcluster delete <name> -n <namespace>
oc delete namespace <name> --ignore-not-found
oc delete cronjob <name> -n default --ignore-not-found
oc delete secret <name>-spoke-kubeconfig -n openshift-pipelines --ignore-not-found
```

A namespace `<name>` that an earlier version of the pipeline created carries no label. `seed-test-vcluster` refuses it and `delete-test-vcluster` keeps it; delete it with the command above.

## CLI reference

### fleet-create-test-vcluster

| Argument | Required | Effect |
|---|---|---|
| `--cluster-name` | Yes | Name of the vCluster |
| `--namespace` | Yes | Namespace of the hub in which the vCluster runs |
| `--output-dir` | Yes | Directory that receives the file `kubeconfig` and the generated values file `vcluster-values.yaml` |
| `--values-file` | No | Values file to use in place of the generated values |
| `--extra-sans` | No | Names to add to the certificate of the vCluster API |
| `--route-san` | No | Host name of the passthrough Route. It is also added to the certificate and set as the server of the kubeconfig. |

The tool exits with 1 when the [name check](#name-check) fails, when `vcluster create` fails, when the Secret `vc-<name>` cannot be read, and when the Route cannot be created.

### fleet-seed-test-vcluster

| Argument | Required | Effect |
|---|---|---|
| `--cluster-name` | Yes | Name of the namespace for the hub resources and of the ManagedCluster |
| `--kubeconfig-file` | Yes | Path of the kubeconfig that `fleet-create-test-vcluster` wrote |
| `--tier` | Yes | Value of the label `tier` of the ManagedCluster |
| `--create-aws-creds` | No | Creates the placeholder Secret `aws-credentials` |

The Task and the pipeline give `tier` the default `base`. The tool does not check the value. It exits with 1 when the [name check](#name-check) fails and when a resource cannot be created.

### fleet-run-post-provision

| Argument | Required | Effect |
|---|---|---|
| `--cluster-name` | Yes | Cluster name of the `post-provision` run |
| `--tier` | Yes | Tier of the `post-provision` run |
| `--namespace` | Yes | Written to the log only |
| `--pipeline-image` | No | Image of the task steps of the run; default `quay.io/rhopl/fleet-pipeline:latest` |
| `--timeout` | No | Seconds to wait for the run; default 600 |

The run gets `openshift-cluster=false`, `spoke-kubeconfig=<name>-admin-kubeconfig`, and placeholders for the Keycloak parameters and `dns-zones`. The tool exits with 1 when the run fails and when the timeout passes.

### fleet-delete-test-vcluster

| Argument | Required | Effect |
|---|---|---|
| `--cluster-name` | Yes | Name of the ManagedCluster and of the vCluster |
| `--namespace` | Yes | Namespace of the vCluster |

[Cleanup](#cleanup) lists the steps and the exit code.

## Differences from a real cluster

| Aspect | Real cluster | vCluster test |
|---|---|---|
| Cluster | Installed by Hive on AWS | Created by `vcluster create` in a namespace of the hub |
| Kubeconfig | The Secret that the ClusterDeployment names | The Secret `<name>-admin-kubeconfig`, named by the parameter `spoke-kubeconfig` |
| ManagedCluster | Applied from the cluster directory and joined by ACM | A stub with `cloud=vcluster` and `vendor=Kubernetes` |
| OAuth, TLS certificate, RBAC, access paste | Configured | Skipped |
| Values of `metadata.yaml` | Passed by `trigger-post-provision` | Not passed; the defaults apply |
| Keycloak parameters and `dns-zones` | From the ConfigMap and the ClusterDeployment | Placeholders |
