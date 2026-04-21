# Plan: GitHub Actions Workflow for fleet-pipeline Image Build

## Context

The `fleet-pipeline` container image is used by all Tekton pipeline tasks (provision and deprovision) but has no automated build/push workflow. Currently the Dockerfile exists at repo root but images must be built and pushed manually. This feature adds a GitHub Actions workflow triggered by release tags that builds, tags, and pushes the image to `quay.io/rhopl/fleet-pipeline`. The existing pipeline references also need updating from the old registry org.

## Changes

### 1. Add `workflow_call` trigger to existing CI workflow

**File:** `.github/workflows/ci.yml`

Add `workflow_call:` to the `on:` block so the build workflow can gate on CI passing:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_call:
```

No other changes to ci.yml.

### 2. Create build-image workflow

**File:** `.github/workflows/build-image.yml` (new)

```yaml
name: Build and Push Container Image

on:
  push:
    tags:
      - v*

jobs:
  ci:
    uses: ./.github/workflows/ci.yml

  build-push:
    runs-on: ubuntu-latest
    needs: ci
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: quay.io
          username: ${{ secrets.QUAY_USERNAME }}
          password: ${{ secrets.QUAY_PASSWORD }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: quay.io/rhopl/fleet-pipeline
          tags: |
            type=semver,pattern={{version}}
            type=raw,value=latest

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          platforms: linux/amd64,linux/arm64
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**How it works:**
- Tag push `v1.2.0` triggers the workflow
- `ci` job runs all existing checks (gitleaks, tox, tekton-lint, kustomize validation) via `workflow_call`
- `build-push` job runs only after CI passes
- `docker/metadata-action` strips the `v` prefix: `v1.2.0` -> image tags `1.2.0` + `latest`
- Multi-arch build (amd64 + arm64) using buildx + QEMU
- Layer cache via GitHub Actions cache

### 3. Update image references in Tekton pipelines

**File:** `tekton/pipelines/provision.yaml` (line 24)
```
- default: quay.io/redhat-openshift-partner-labs/fleet-pipeline:latest
+ default: quay.io/rhopl/fleet-pipeline:latest
```

**File:** `tekton/pipelines/deprovision.yaml` (line 12)
```
- default: quay.io/redhat-openshift-partner-labs/fleet-pipeline:latest
+ default: quay.io/rhopl/fleet-pipeline:latest
```

### 4. User action: configure GitHub secrets

Two secrets needed in repo Settings > Secrets and variables > Actions:
- `QUAY_USERNAME` — Quay.io robot account or username
- `QUAY_PASSWORD` — Corresponding token/password

## Verification

1. **Workflow YAML syntax** — push to feature branch, GitHub validates on PR
2. **CI reuse** — confirm `workflow_call` works by checking Actions tab on tag push
3. **Image references** — `grep -r "quay.io/redhat-openshift-partner-labs" tekton/` should return 0 matches after update
4. **Local Dockerfile** — `docker build -t fleet-pipeline:local .` to confirm image builds
5. **End-to-end** — create and push a test tag (`git tag v0.1.0 && git push origin v0.1.0`), verify image appears at `quay.io/rhopl/fleet-pipeline` with tags `0.1.0` and `latest`
