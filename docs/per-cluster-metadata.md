# Per-Cluster Metadata

This document describes the keys of `metadata.yaml`: the default, the accepted values and the effect of each.

`metadata.yaml` holds the values that differ between clusters. Values that are the same for every cluster are in the ConfigMap `fleet-pipeline-config`; see [hub-setup.md](hub-setup.md#6-set-the-pipeline-configuration). [parameter-threading.md](parameter-threading.md) describes how a value of the file reaches a task, and how to add a key.

## The file

```
provision/<name>/
├── kustomization.yaml
├── metadata.yaml
├── hive/
└── crossplane/
```

The file is a flat YAML map:

```yaml
platform: aws
aws-credentials-mode: scoped
htpasswd-provider-name: "Partner IDP"
```

`fleet-scaffold-cluster` writes the file with `platform` and, for AWS, `aws-credentials-mode`. Its arguments `--htpasswd-provider-name` and `--ai-accelerator` add those keys. Edit the file to set the other keys.

The file is optional. A missing or empty file gives every key its default.

## Supported keys

| Key | Default | Accepted values | Read by | Effect |
|---|---|---|---|---|
| `htpasswd-provider-name` | `htpasswd` | Any text | `configure-spoke-oauth` | Display name of the htpasswd identity provider on the spoke |
| `openshift-ai-version` | `v3` | `v2`, `v3` | `apply-ai-workloads` | OpenShift AI version of an `ai` cluster and its prerequisite operators |
| `ai-accelerator` | `nvidia-gpu` | `none`, `nvidia-gpu` | `apply-ai-workloads`, and the condition of `add-ai-workers` | Hardware profile of an `ai` cluster; see [AI accelerator](#ai-accelerator) |
| `platform` | `aws` | `aws`, `azure` | No task | Cloud platform of the cluster |
| `aws-credentials-mode` | `legacy` | `scoped`; every other value counts as `legacy` | The conditions of `wait-for-aws-component-credentials`, `build-aws-credentials-manifests` and `scope-aws-credentials` | How the spoke gets its AWS credentials; see [AWS credential mode](#aws-credential-mode) |
| `timezone` | `America/Chicago` | An IANA timezone name | `create-cluster-cronjob` | Timezone of the cluster job on the hub |
| `schedule` | `00 08 * * 1-5` | A five-field cron expression | `create-cluster-cronjob` | Schedule of the cluster job on the hub |
| `podvm-instance-type` | Empty | One EC2 instance type, `<family>.<size>` | `apply-coco-workloads` | Instance type of the peer pod VMs of a `coco` cluster |

## Validation

`read-cluster-metadata` reads the file in `pre-provision` and again in `provision`. It checks four keys, whatever the tier of the cluster, and fails the run on an invalid value:

| Key | Message |
|---|---|
| The file is not a map | `metadata.yaml must contain a YAML object` |
| `ai-accelerator` | `Invalid ai-accelerator value: <value>; expected one of ['none', 'nvidia-gpu']` |
| `timezone` | `Invalid timezone value: <value>; expected an IANA timezone name` |
| `schedule` | `Invalid schedule value: <value>; expected a five-field cron expression` |
| `podvm-instance-type` | `Invalid podvm-instance-type value: <value>` |

`openshift-ai-version` is checked later: `apply-ai-workloads` rejects a value other than `v2` and `v3`. The other keys are not checked.

## Key details

### AI accelerator

`ai-accelerator` applies to `tier=ai`. The other tiers do not use it.

| Value | Effect |
|---|---|
| `none` | Installs CPU-only OpenShift AI. Skips Node Feature Discovery, the NVIDIA GPU Operator, the GPU ClusterPolicy and the AI worker MachinePool. |
| `nvidia-gpu` | Requires Node Feature Discovery and the NVIDIA GPU Operator in the spoke catalog, installs the GPU-backed OpenShift AI stack, and creates the AI worker MachinePool. |

Before it applies a Subscription, `apply-ai-workloads` checks that the spoke catalog offers every operator that the selected `openshift-ai-version` and `ai-accelerator` need. A CPU-only cluster is not checked for Node Feature Discovery or the NVIDIA GPU Operator.

### AWS credential mode

`aws-credentials-mode: scoped` gives the spoke one AWS credential per operator, limited to the cluster. Without the key the cluster is `legacy`. [architecture.md](architecture.md#aws-credential-modes) describes both modes.

### Cluster job

`create-cluster-cronjob` creates a CronJob named after the cluster in the namespace `default` of the hub. `timezone` and `schedule` set when it runs.

```yaml
timezone: America/Chicago
schedule: "00 08 * * 1-5"
```

- The CronJob runs as the ServiceAccount `ecoeng`, which must exist; see [hub-setup.md](hub-setup.md#10-check-the-account-of-the-cluster-job).
- The CronJob runs the image `quay.io/rhopl/osplc:v0.0.2`.
- The task pulls the pipeline image on every run, so the tag `latest` cannot resolve to an older cached image.
- `deprovision` deletes the CronJob before it deletes the cluster namespace. The CronJob is outside that namespace, so deleting the namespace does not remove it.

### Pod VM instance type

`podvm-instance-type` is the EC2 instance type of the peer pod VMs of a `coco` cluster; see [coco-tier.md](coco-tier.md). `fleet-scaffold-cluster` writes it for that tier and checks it against the instance types that support AMD SEV-SNP.

```yaml
podvm-instance-type: m6a.large
```

- fleet has no default for the key.
- For `tier=coco`, `apply-coco-workloads` fails on an empty value with `podvm-instance-type is empty for <name>; regenerate the overlay with the current fleet-cluster-scaffold`.
- The other tiers do not use the value.

## Limit

A `post-provision` run that the EventListener starts for a request with `action: post-provision` receives no value of `metadata.yaml`. It runs with the defaults of the table. For an `ai` cluster that means `v3` and `nvidia-gpu`; for a `coco` cluster the run fails at `apply-coco-workloads`, because `podvm-instance-type` is empty.

To run `post-provision` again with the values of the file, start it with the parameters of an earlier run; see the [user guide](user-guide.md#run-a-pipeline-again).
