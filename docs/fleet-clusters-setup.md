# fleet-clusters Repository Setup

The [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) repo holds cluster lifecycle state — specs, templates, and archive records. The fleet repo's Tekton pipelines react to changes pushed here via webhooks.

## Repository Structure

```
cluster-templates/      — Kustomize bases for cluster specs (by tier)
provision/              — Active cluster specs (one directory per cluster)
deprovision/            — Sentinel files that trigger cluster teardown
archive/                — Completed lifecycle records (moved from provision/)
```

### Sentinel Files

**Provision**: push a directory to `provision/<cluster-name>/` containing the cluster's Kustomize overlay (kustomization.yaml, patches, etc.). The push event triggers the pre-provision pipeline.

**Deprovision**: push a file to `deprovision/<cluster-name>-archive`. The filename suffix `-archive` is stripped by the CEL overlay to extract the cluster name. The push event triggers the deprovision pipeline.

## GitHub App Configuration

The `create-deployment-status` task uses a GitHub App to write deployment statuses back to fleet-clusters. This enables GitHub Actions in fleet-clusters to react to pipeline completion (e.g., archiving deprovisioned clusters).

### Required Permissions

- **Deployments**: Read & Write

### Setup

1. Create a GitHub App (or use an existing one) with Deployments read/write permission.
2. Install the app on the `fleet-clusters` repository.
3. Note the **App ID** and **Installation ID**.
4. Generate a private key and store it as a Kubernetes Secret on the hub cluster:
   ```bash
   kubectl create secret generic fleet-github-app-key \
     --namespace openshift-pipelines \
     --from-file=private-key=/path/to/private-key.pem
   ```
5. Update `fleet-pipeline-config` ConfigMap with the app credentials:
   ```yaml
   github-app-id: "<app-id>"
   github-app-installation-id: "<installation-id>"
   github-app-key-secret: "fleet-github-app-key"
   clusters-repo: "redhat-openshift-partner-labs/fleet-clusters"
   ```

## Webhook Configuration

Configure a GitHub webhook on fleet-clusters to send push events to the hub cluster's EventListener.

- **Payload URL**: `https://<hub-eventlistener-route>/`
- **Content type**: `application/json`
- **Secret**: must match the `fleet-webhook-secret` Kubernetes Secret
- **Events**: Push events only

The EventListener has two triggers:
- **pre-provision**: fires when files are added under `provision/`
- **deprovision**: fires when files are added under `deprovision/`

## Archive Workflow

After the deprovision pipeline completes, `create-deployment-status` posts a GitHub deployment status with `environment: deprovision` and `state: success`. A GitHub Action in fleet-clusters reacts to this event to archive the cluster:

1. `git mv provision/<cluster-name> archive/<cluster-name>`
2. `rm deprovision/<cluster-name>-archive`
3. Opens a PR and enables auto-merge

See [`docs/examples/fleet-clusters-archive-workflow.yml`](examples/fleet-clusters-archive-workflow.yml) for a reference workflow.

## Migration from In-Repo Clusters

If you have existing cluster directories under `fleet/clusters/`:

1. Copy cluster-templates to `fleet-clusters/cluster-templates/`
2. For each active cluster, copy `clusters/<name>/` to `fleet-clusters/provision/<name>/`
3. Update each cluster's `kustomization.yaml` to reference the new `cluster-templates/` path
4. Verify with `kustomize build` on each cluster directory
5. Remove `clusters/` and `cluster-templates/` from the fleet repo once migration is confirmed
