# Per-Cluster Metadata

Per-cluster metadata provides a way to configure cluster-specific values that vary between clusters and are not appropriate for the global `fleet-pipeline-config` ConfigMap. Values are defined in a `metadata.yaml` file within each cluster's directory in fleet-clusters and threaded through the pipeline system.

## metadata.yaml

Each cluster directory can contain a `metadata.yaml` file:

```
provision/<cluster-name>/
  ├── kustomization.yaml
  ├── metadata.yaml              ← per-cluster configuration
  ├── hive/
  │   └── ...
  └── crossplane/
      └── ...
```

The file is a flat YAML map of key-value pairs:

```yaml
# provision/eager-falcon/metadata.yaml
htpasswd-provider-name: "PartnerIDP"
```

If the file is missing or empty, all values fall back to their defaults. This makes metadata.yaml optional — existing clusters without one continue to work unchanged.

## Supported keys

| Key | Default | Used by | Description |
|-----|---------|---------|-------------|
| `htpasswd-provider-name` | `htpasswd` | `configure-spoke-oauth` | Display name for the htpasswd identity provider in the spoke's OAuth configuration |

## How values flow through the pipeline

Metadata follows the same threading pattern as `tier` — read during provision, forwarded through `trigger-post-provision`, and consumed in post-provision:

```
provision pipeline
  │
  ├─ git-clone (clones fleet-clusters to workspace)
  │
  ├─ read-cluster-metadata
  │    reads: provision/<cluster-name>/metadata.yaml
  │    returns: htpasswd-provider-name (result)
  │
  └─ trigger-post-provision
       receives: htpasswd-provider-name from read-cluster-metadata result
       embeds it in the PipelineRun YAML for post-provision
            │
            ▼
post-provision pipeline
  │
  └─ configure-spoke-oauth
       receives: htpasswd-provider-name as pipeline param
       uses it in the OAuth CR's htpasswd identity provider name
```

### Where defaults are applied

Defaults live in the Tekton Task YAML (`read-cluster-metadata.yaml`), not in the Python CLI tool. The CLI outputs raw JSON from `metadata.yaml`; the bash stub uses `jq` with a fallback:

```bash
echo "$META" | jq -r '.["htpasswd-provider-name"] // "htpasswd"'
```

This keeps the Python CLI generic while centralizing default logic in one place per value.

## Adding a new per-cluster value

When you need a new cluster-specific configuration value:

### 1. Add a result to the read-cluster-metadata Task

In `tekton/tasks/read-cluster-metadata.yaml`, add a new result and a `jq` extraction line:

```yaml
results:
  - name: htpasswd-provider-name
  - name: my-new-value              # add result
steps:
  - script: |
      # ... existing extractions ...
      echo "$META" | jq -r '.["my-new-value"] // "default-value"' \
        | tee "$(results.my-new-value.path)"
```

### 2. Forward through trigger-post-provision

Add an argparse argument to `fleet/tasks/trigger_post_provision.py`:

```python
parser.add_argument("--my-new-value", default="default-value")
```

Include it in the PipelineRun YAML template and in the Tekton Task YAML (`tekton/tasks/trigger-post-provision.yaml`).

### 3. Add the pipeline param to post-provision

In `tekton/pipelines/post-provision.yaml`, add a param with the same default and wire it to the consuming task.

### 4. Wire the provision pipeline

In `tekton/pipelines/provision.yaml`, pass the new result from `read-cluster-metadata` to `trigger-post-provision`.

### 5. Add the argparse argument to the consuming Python CLI

Add the corresponding `--my-new-value` argument and use it in the task logic.

### 6. Update this document

Add the new key to the "Supported keys" table above.

## Relationship to fleet-pipeline-config

The `fleet-pipeline-config` ConfigMap holds **global defaults** — values that are the same across all clusters (Keycloak URL, base domain, pipeline image, etc.). The `config-loader` Task resolves these at pipeline start.

`metadata.yaml` holds **per-cluster overrides** — values that differ between clusters. The distinction:

| Scope | Source | Example |
|-------|--------|---------|
| All clusters | `fleet-pipeline-config` ConfigMap | `keycloak-url`, `pipeline-image`, `provider-name` |
| Per cluster | `metadata.yaml` in fleet-clusters | `htpasswd-provider-name` |

## CLI reference

The `fleet-read-cluster-metadata` CLI tool reads `metadata.yaml` and outputs JSON:

```bash
fleet-read-cluster-metadata --cluster-dir /path/to/provision/cluster-name
# Output: {"htpasswd-provider-name": "PartnerIDP"}
```

If `metadata.yaml` is missing or empty, it outputs `{}`. If the directory does not exist, it exits with code 1.
