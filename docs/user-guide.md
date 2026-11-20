# User Guide

This guide describes the tasks an operator performs: provision a cluster, hand over access, monitor a run, deprovision a cluster, and recover from a failed task.

[architecture.md](architecture.md) lists every task of every pipeline. The setup of the hub is in [hub-setup.md](hub-setup.md).

In every command, `<name>` is the cluster name. The pipelines run in the namespace `openshift-pipelines` on the hub.

## Prerequisites

| You need | Detail |
|---|---|
| Push access to [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) | Cluster definitions and deprovision requests are commits to that repository. |
| `oc` logged in to the hub as a cluster administrator | The checks in this guide read cluster-scoped resources. |
| `tkn` | [Tekton CLI](https://tekton.dev/docs/cli/) |
| `fleet-scaffold-cluster` | Installed from [fleet-cluster-scaffold](https://github.com/redhat-openshift-partner-labs/fleet-cluster-scaffold) with `pip install .`. It needs `kustomize`, and `oc` with network access to `quay.io`. |

The hub must be set up as [hub-setup.md](hub-setup.md) describes. Each command below prints the named resource when that part is in place.

| Part | Check |
|---|---|
| Pipelines | `oc get pipelines -n openshift-pipelines` lists `pre-provision`, `provision`, `post-provision` and `deprovision` |
| Webhook receiver | `oc get eventlistener fleet-cluster-lifecycle -n openshift-pipelines` |
| Pull secret of the pipeline image | `oc get secret fleet-pipeline-pull-secret -n openshift-pipelines` |
| Keycloak admin Secret | `oc get secret keycloak-admin -n openshift-pipelines`. `keycloak-admin-secret` in ConfigMap `fleet-pipeline-config` holds the name; `keycloak-admin` is the default. |
| Crossplane AWS provider | `oc get providers.pkg.crossplane.io` shows the provider as `HEALTHY` |

## Provision a cluster

### 1. Choose the name, the region and the tier

- Name: lowercase letters, digits and hyphens, at most 49 characters. The AWS infra prefix that the name produces must differ from the prefix of every other cluster; `check-prefix-collision` fails the run otherwise.
- Tier: `base`, `virt`, `ai` or `coco`. See [Tiers](#tiers).

### 2. Create the cluster directory

Run the scaffold from the root of your fleet-clusters checkout:

```bash
fleet-scaffold-cluster aws --name <name> --region us-east-1 --tier base --base-path provision
```

Expected output:

```text
Scaffolding aws/standard cluster '<name>' in provision/
  -> wrote provision/<name>
  -> hive: OK
  -> crossplane: OK
  -> release check:
  ...
  -> -> Cluster '<name>' scaffolded successfully
```

The command writes `provision/<name>/` with `kustomization.yaml`, `metadata.yaml`, `hive/` and `crossplane/`. The [scaffold README](https://github.com/redhat-openshift-partner-labs/fleet-cluster-scaffold#command-reference) lists every argument. A `coco` cluster needs more arguments; see [coco-tier.md](coco-tier.md#create-the-overlay).

Do not copy the directory of another cluster. The pipelines read annotations that the scaffold writes, and a directory without them fails `pre-provision`.

### 3. Set per-cluster values

`provision/<name>/metadata.yaml` holds values for this cluster only, such as `openshift-ai-version`, `ai-accelerator`, `timezone` and `schedule`. [per-cluster-metadata.md](per-cluster-metadata.md#supported-keys) lists the keys and their defaults.

### 4. Commit and merge

```bash
git checkout -b feat/add-<name>
git add provision/<name>
git commit -S -s -m "feat(clusters): add <name>"
git push origin feat/add-<name>
```

Open a pull request and merge it to `main`.

- Add one cluster per push. The EventListener reads one cluster name from a push.
- A push starts a run only when it adds a file under `provision/`. A push that only changes existing files starts no run; see [Run a pipeline again](#run-a-pipeline-again).
- A commit message that contains `[skip-provision]` prevents the run.

### 5. Wait for the three pipelines

The merge starts `pre-provision`. Each pipeline starts the next one with its last task.

| Pipeline | PipelineRun name | Result | Longest wait | Tasks |
|---|---|---|---|---|
| `pre-provision` | `pre-provision-<name>-*` | Namespace `<name>` on the hub with the SSH key, the pull secret and the AWS credentials | 10 minutes for each wait for AWS credentials | [architecture.md](architecture.md#pre-provision) |
| `provision` | `provision-<name>-*` | Installed cluster, registered in ACM, labelled `provisioned=true` | 1 hour 15 minutes for the install | [architecture.md](architecture.md#provision) |
| `post-provision` | `post-provision-<name>-*` | OAuth, TLS certificate, RBAC and tier workloads on the spoke; access details published | 5 hours for the whole run | [architecture.md](architecture.md#post-provision) |

### 6. Confirm the result

```bash
tkn pipelinerun list -n openshift-pipelines
```

The three runs of the cluster show `Succeeded`.

```bash
oc get clusterdeployment <name> -n <name>
```

The column `INSTALLED` shows `true`.

```bash
oc get managedcluster <name> --show-labels
```

The columns `JOINED` and `AVAILABLE` show `True`, and the labels include `tier=<tier>` and `provisioned=true`.

## Tiers

The scaffold writes the tier as the label `tier` of the ManagedCluster. `post-provision` installs the workloads of that tier. `read-cluster-tier` fails the `provision` run for any other value.

| Tier | Installed on the spoke | Input beyond the scaffold arguments | Reference |
|---|---|---|---|
| `base` | OAuth, TLS certificate, RBAC and the `workloads/base` overlay. Every tier includes these. | None | [architecture.md](architecture.md#post-provision) |
| `virt` | OpenShift Virtualization, and Node Feature Discovery when the spoke catalog has it. The hub adds a bare-metal worker MachinePool. | None | [architecture.md](architecture.md#post-provision) |
| `ai` | OpenShift AI 2.x or 3.x. With `ai-accelerator: nvidia-gpu`, also the GPU operators and a GPU worker MachinePool. | `openshift-ai-version`, `ai-accelerator` | [per-cluster-metadata.md](per-cluster-metadata.md#ai-accelerator), [ai-tier.md](ai-tier.md) |
| `coco` | OpenShift sandboxed containers with peer pods on AWS | Region, OpenShift version and pod VM instance type have limits | [coco-tier.md](coco-tier.md) |

## Hand over access

`create-access-paste` uploads the console URL, the kubeadmin password and the kubeconfig as one password-protected PrivateBin paste. It stores the paste URL and the paste password in Secret `<name>-access-paste`.

Print the URL:

```bash
oc get secret <name>-access-paste -n openshift-pipelines -o jsonpath='{.data.url}' | base64 -d
```

Print the password:

```bash
oc get secret <name>-access-paste -n openshift-pipelines -o jsonpath='{.data.password}' | base64 -d
```

The paste expires after one week. `privatebin-expire` in ConfigMap `fleet-pipeline-config` sets the lifetime.

## Monitor a run

| Goal | Command |
|---|---|
| List the runs | `tkn pipelinerun list -n openshift-pipelines` |
| Follow the log of a run | `tkn pipelinerun logs <pipelinerun> -n openshift-pipelines -f` |
| See the state of each task | `tkn pipelinerun describe <pipelinerun> -n openshift-pipelines` |
| Read the log of one task | `tkn taskrun logs <taskrun> -n openshift-pipelines` |

`tkn pipelinerun describe` prints the TaskRun names. Each log line starts with the task name in square brackets.

In the OpenShift console, open **Pipelines → PipelineRuns** in the project `openshift-pipelines`.

## Run a pipeline again

A run does not resume. A new run starts at the first task of the pipeline.

### After a failure outside the cluster directory

Use this for a timeout or a hub error. The new run takes its parameters, its service account and its workspace from the failed run:

```bash
tkn pipeline start <pipeline> --use-pipelinerun <failed-pipelinerun> -n openshift-pipelines
```

A new `pre-provision` or `provision` run starts the pipelines after it again.

### After a fix to the cluster directory

A push that only changes existing files starts no run. Create the `pre-provision` run for the fixed revision yourself. Replace `<name>` and `<commit-sha>`:

```bash
oc create -n openshift-pipelines -f - <<'EOF'
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  generateName: pre-provision-<name>-
spec:
  pipelineRef:
    name: pre-provision
  params:
    - name: cluster-name
      value: <name>
    - name: git-repo-url
      value: git@github.com:redhat-openshift-partner-labs/fleet-clusters.git
    - name: git-revision
      value: <commit-sha>
  taskRunTemplate:
    serviceAccountName: fleet-pipeline
    podTemplate:
      securityContext:
        fsGroup: 0
      imagePullSecrets:
        - name: fleet-pipeline-pull-secret
  workspaces:
    - name: shared-workspace
      volumeClaimTemplate:
        spec:
          accessModes:
            - ReadWriteOnce
          resources:
            requests:
              storage: 1Gi
          storageClassName: gp3-csi
EOF
```

The manifest equals the one in [triggertemplate-pre-provision.yaml](../tekton/triggers/triggertemplate-pre-provision.yaml).

## Deprovision a cluster

### 1. Add the sentinel file

In your fleet-clusters checkout:

```bash
git checkout -b feat/remove-<name>
touch deprovision/<name>-archive
git add deprovision/<name>-archive
git commit -S -s -m "feat(clusters): deprovision <name>"
git push origin feat/remove-<name>
```

Open a pull request and merge it to `main`.

- The file name must end in `-archive`.
- A commit message that contains `[skip-deprovision]` prevents the run.

### 2. Wait for the pipeline

The merge starts the run `deprovision-<name>-*`. It deletes the cluster resources, waits up to 30 minutes for Hive to uninstall the cluster, deletes the hub artifacts and the IAM resources, and checks that nothing remains. [architecture.md](architecture.md#deprovision) lists the tasks.

### 3. Confirm the result

```bash
oc get namespace <name>
```

The command reports `NotFound`.

```bash
oc get managedcluster <name>
```

The command reports `NotFound`.

In fleet-clusters, the archive workflow has moved `provision/<name>` to `archive/<name>` and removed `deprovision/<name>-archive`.

## IAM resources that remain

`cleanup-hub-artifacts` waits 10 minutes for Crossplane to delete the IAM resources of the cluster. If resources remain, the task fails and keeps the namespace `<name>`. [architecture.md](architecture.md#iam-cleanup-at-deprovision) describes the rule.

### 1. Find the cause

List what remains:

```bash
oc get accesskeys.iam.aws.upbound.io,roles.iam.aws.upbound.io,policies.iam.aws.upbound.io -l openshiftpartnerlabs.com/cluster=<name>
```

The task log shows the AWS name and the conditions of each remaining resource.

### 2. Run deprovision again

When the cause is fixed, start the pipeline again as described in [Run a pipeline again](#run-a-pipeline-again).

### 3. Release the resources when Crossplane cannot reach AWS

This run removes the Crossplane finalizers and leaves the IAM resources in AWS for manual cleanup:

```bash
tkn pipeline start deprovision -p cluster-name=<name> -p orphan-stuck-iam=true --serviceaccount fleet-pipeline -n openshift-pipelines
```

The task prints a report of the resources it released and saves it in a ConfigMap in `openshift-pipelines`. The log names the ConfigMap.

| Report status | Meaning |
|---|---|
| `confirmed_present` | The resource existed in AWS at the time in the report. Check AWS again before you delete it. |
| `needs_check` | The task could not read the resource in AWS. |

The task reads AWS with the optional Secret `fleet-iam-read-only` in `openshift-pipelines`. Without the Secret, every item is `needs_check`.

| Key of `fleet-iam-read-only` | Value |
|---|---|
| `FLEET_IAM_AWS_ACCOUNT` | AWS account that owns the IAM resources of the clusters |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Credential that has only `iam:GetUser`, `iam:GetRole` and `iam:GetPolicy` |
| `AWS_SESSION_TOKEN` | Needed for a temporary credential |

### 4. Clean up in AWS

The archive workflow writes the pending items to `archive/<name>/iam.cleanup.json` in fleet-clusters. Delete each listed resource in AWS. A deprovision without remaining resources writes no such file.

### Retry report delivery

| Situation | Action |
|---|---|
| `verify-deprovision` succeeded and `create-deployment-status` failed | Run only the Task `create-deployment-status` again in `openshift-pipelines`, with the parameters of the failed run and the service account `fleet-pipeline`. The task reads the saved reports by cluster name. |
| GitHub accepted the deployment and the archive job failed | Run the archive job again in fleet-clusters. |
| GitHub rejected the report because of its size | Export the report as shown below, then follow the manual archive procedure in the fleet-clusters README. |

Keep the ConfigMaps until the archive commit contains the report. List them:

```bash
oc get configmaps -n openshift-pipelines -l "openshiftpartnerlabs.com/iam-cleanup-cluster=<name>"
```

Export the full report. Run this where the `fleet` package is installed and `oc` is logged in to the hub:

```bash
python3 -c 'import json, sys; from fleet.tasks._iam_cleanup import load_report; print(json.dumps(load_report(sys.argv[1]), indent=2))' <name> > iam.cleanup.json
```

## Troubleshooting

Find the failed task with `tkn pipelinerun describe`, read its log, and look up the task below. After the fix, see [Run a pipeline again](#run-a-pipeline-again).

### pre-provision

| Task | The log shows | Check | Action |
|---|---|---|---|
| `check-prefix-collision` | `Infra prefix collision detected for cluster '<name>'` and the colliding clusters | None | Choose another name and create the directory again. |
| `wait-for-aws-credentials` | `Timed out after 600s waiting for aws-credentials-raw` | `oc get accesskeys.iam.aws.upbound.io -l openshiftpartnerlabs.com/cluster=<name>` and `oc get providers.pkg.crossplane.io` | Fix the provider credentials; see [hub-config/README.md](../hub-config/README.md#credentials-setup). |
| `wait-for-aws-component-credentials` | `Timed out after 600s waiting for scoped AWS credentials`, then each resource that is not ready with its message | The message of each resource, for example an AWS `AccessDenied` | Give the hub's Crossplane identity the missing IAM actions; see [hub-config/README.md](../hub-config/README.md#credentials-setup). |
| `wait-for-aws-component-credentials` | `regenerate the overlay with the current fleet-cluster-scaffold` | `fleet-scaffold-cluster --version` | Install the current scaffold and create the directory again. |
| `validate-cluster-inputs` | `MISSING Secret '<secret>'` or `MISSING ClusterImageSet '<image-set>'` | `oc get secrets -n <name>` and `oc get clusterimagesets` | Create the missing resource, or set an image set that exists. |

### provision

| Task | The log shows | Check | Action |
|---|---|---|---|
| `apply-cluster-crs` | `kustomize build stderr:` and the build error | `kustomize build provision/<name>/hive` in fleet-clusters | Fix the directory. |
| `wait-for-hive-ready` | `ClusterDeployment not provisioned` | `oc get clusterdeployment <name> -n <name> -o yaml` and `oc logs -n <name> -l hive.openshift.io/cluster-deployment-name=<name> --tail=100` | Fix the cause the install log names. |
| `wait-for-managed-cluster` | `ManagedCluster not joined` | `oc get managedcluster <name> -o yaml` | Fix the condition that is not `True`. |
| `read-cluster-tier` | `Tier '<tier>' is not supported by this pipeline image` or `Tier label is empty on ManagedCluster` | `oc get managedcluster <name> --show-labels` | Set a supported tier in the directory, or update the pipeline image. |

### post-provision

| Task | The log shows | Check | Action |
|---|---|---|---|
| `register-keycloak-client` | `Failed to get Keycloak admin token (HTTP <code>)` or `Realm '<realm>' not found` | `oc get secret keycloak-admin -n openshift-pipelines`, and `keycloak-url` and `keycloak-realm` in ConfigMap `fleet-pipeline-config` | Correct the Secret or the ConfigMap value. |
| `wait-for-ssl-ready` | `Certificate not ready` | `oc describe certificate <name>-wildcard-certificate -n openshift-ingress` and `oc describe clusterissuer letsencrypt-<name>` | Fix the cause the conditions name. |
| `create-access-paste` | `Failed to create PrivateBin paste` | `privatebin-url` in ConfigMap `fleet-pipeline-config` | Correct the URL, or restore the PrivateBin service. |

The tasks of the `coco` tier are in [coco-tier.md](coco-tier.md#failure-messages).

### deprovision

| Task | The log shows | Check | Action |
|---|---|---|---|
| `wait-hive-uninstall` | `Timed out waiting for ClusterDeployment '<name>' deletion` | `oc get clusterdeprovision -n <name> -o yaml` | Fix the cause the conditions name. |
| `wait-hive-uninstall` | `Could not check ClusterDeployment` | `oc whoami` on the hub | Run the pipeline again when the hub API answers. The run stops before it deletes the installer credentials. |
| `cleanup-hub-artifacts` | The AWS name and the conditions of each IAM resource that remains | See [IAM resources that remain](#iam-resources-that-remain) | See [IAM resources that remain](#iam-resources-that-remain). |
| `create-deployment-status` | An error from the GitHub API | See [Retry report delivery](#retry-report-delivery) | See [Retry report delivery](#retry-report-delivery). |

## Related documentation

| Document | Covers |
|---|---|
| [architecture.md](architecture.md) | Components, trust boundary, and the tasks of each pipeline |
| [per-cluster-metadata.md](per-cluster-metadata.md) | The `metadata.yaml` keys |
| [coco-tier.md](coco-tier.md) | Prerequisites, limits and failure messages of the `coco` tier |
| [ai-tier.md](ai-tier.md) | Inputs, operators, install order and failure messages of the `ai` tier |
| [fleet-clusters-setup.md](fleet-clusters-setup.md) | Repository structure, GitHub App, webhook, archive workflow |
| [hub-setup.md](hub-setup.md) | The one-time setup of the hub cluster |
