# fleet-clusters Setup

This guide describes how to connect the fleet-clusters repository to the hub: the repository layout, the triggers, the webhook, the GitHub App, and the archive workflow.

It is step 9 of the [hub setup](hub-setup.md). The EventListener and its Route must exist before the webhook is created.

## Repository layout

[fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) holds the definition of every cluster.

| Path | Holds |
|---|---|
| `provision/<name>/` | The directory of one cluster, written by `fleet-scaffold-cluster`: `kustomization.yaml`, `metadata.yaml`, `hive/` and `crossplane/` |
| `deprovision/<name>-archive` | An empty file that requests the deprovision of `<name>` |
| `archive/<name>/` | The directory of a deprovisioned cluster, moved there by the archive workflow |
| `cluster-templates/` | The base templates that the cluster directories reference |

The [user guide](user-guide.md) describes how an operator adds a cluster directory and a deprovision file. [per-cluster-metadata.md](per-cluster-metadata.md) describes `metadata.yaml`.

## Triggers

The EventListener `fleet-cluster-lifecycle` has two triggers. Both check the signature of the webhook.

| Trigger | Starts the pipeline | Condition | Cluster name |
|---|---|---|---|
| `pre-provision` | `pre-provision` | A GitHub push event with a valid signature, on `refs/heads/main`, in which a commit adds a file under `provision/`, and whose head commit message does not contain `[skip-provision]` | The second path segment of the first added file |
| `deprovision` | `deprovision` | The same, for a file under `deprovision/` and the marker `[skip-deprovision]` | The file name without `-archive` |

- A push starts one run. When a push adds files for several clusters, only the first cluster gets a run.
- A push that only changes or deletes files starts no run.

## Webhook

1. Create the Secret that holds the webhook secret:

   ```bash
   oc create secret generic fleet-webhook-secret \
     --from-literal=WebHookSecretKey="$(openssl rand -hex 32)" \
     -n openshift-pipelines
   ```

2. Print the secret and the host name of the Route:

   ```bash
   oc get secret fleet-webhook-secret -n openshift-pipelines -o jsonpath='{.data.WebHookSecretKey}' | base64 -d
   ```

   ```bash
   oc get route fleet-cluster-lifecycle -n openshift-pipelines -o jsonpath='{.spec.host}'
   ```

3. In fleet-clusters, open **Settings → Webhooks → Add webhook** and set:

   | Field | Value |
   |---|---|
   | Payload URL | `https://<route-host>/` |
   | Content type | `application/json` |
   | Secret | The value of `WebHookSecretKey` |
   | Events | Just the push event |

## GitHub App

`create-deployment-status`, the last task of `deprovision`, creates a GitHub deployment in fleet-clusters. It authenticates as a GitHub App.

1. Create a GitHub App with the repository permission **Deployments: Read and write**.
2. Install the App on fleet-clusters.
3. Note the App ID and the installation ID.
4. Generate a private key for the App and store it on the hub:

   ```bash
   oc create secret generic fleet-github-app-key \
     --from-file=private-key=<private-key.pem> \
     -n openshift-pipelines
   ```

5. Set these keys of the ConfigMap `fleet-pipeline-config`, as step 6 of the [hub setup](hub-setup.md#6-set-the-pipeline-configuration) describes:

   | Key | Value |
   |---|---|
   | `github-app-id` | The App ID |
   | `github-app-installation-id` | The installation ID |
   | `github-app-key-secret` | `fleet-github-app-key`, the default |
   | `clusters-repo` | `redhat-openshift-partner-labs/fleet-clusters`, the default |

## Deployment status

After `verify-deprovision` succeeds, `create-deployment-status` creates a deployment on the ref `main` with the environment `deprovision`, then sets its status to `success`. The deployment carries this payload:

| Field | Value |
|---|---|
| `cluster_name` | The cluster name |
| `pipeline_run_id` | The name of the `deprovision` PipelineRun |
| `iam_cleanup_pending` | `true` when IAM resources were left in AWS |
| `iam_cleanup_report` | The report of those resources; present only when `iam_cleanup_pending` is `true` |

## Archive workflow

The workflow [archive-cluster.yaml](https://github.com/redhat-openshift-partner-labs/fleet-clusters/blob/main/.github/workflows/archive-cluster.yaml) of fleet-clusters runs on a deployment status with the environment `deprovision` and the state `success`. It reads `cluster_name` from the payload and commits to `main`:

1. Moves `provision/<name>` to `archive/<name>`.
2. Removes `deprovision/<name>-archive`.

When `iam_cleanup_pending` is `true`, the workflow must also write `iam_cleanup_report` to `archive/<name>/iam.cleanup.json`. The [user guide](user-guide.md#iam-resources-that-remain) directs the operator to that file.

[examples/fleet-clusters-archive-workflow.yml](examples/fleet-clusters-archive-workflow.yml) is an example of the workflow. It makes the two changes through a pull request and does not write `iam.cleanup.json`.
