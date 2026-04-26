# fleet

> **Status:** 🚧 Early development. Architecture agreed; implementation in progress.

OpenShift cluster fleet management for Red Hat OpenShift Partner Labs. Hub-and-spoke provisioning, post-provisioning configuration, and day-2 operations for OpenShift clusters delivered to third-party partners.

## What lives here

This repo is the **control plane** for our OpenShift fleet. It holds the declarative definitions (cluster specs, tier configs, pipeline definitions) and is the trigger surface for cluster lifecycle operations.

It does **not** hold: day-2 workloads, tenant application manifests, or anything that runs on the spoke clusters long-term. Those belong in sibling repos.

## Architecture at a glance

- **Git** (this repo) — source of truth for cluster definitions and pipelines
- **Tekton** (OpenShift Pipelines) — workflow engine for provision, post-provision, and deprovision
- **ArgoCD** (OpenShift GitOps) — manifest delivery to the hub + day-2 workload delivery to spokes via `ApplicationSet`
- **ACM + Hive** — fleet membership and cluster provisioning
- **cert-manager** — hub-side TLS certificate management; spokes receive only derived artifacts
- **Crossplane** — per-cluster IAM user generation (pre-installed prerequisite, not managed by this repo)

The guiding rule: *ArgoCD reconciles declarative state. Tekton runs ordered workflows. ACM/Hive controls cluster lifecycle.* Each tool does one job.

For day-to-day operations (provisioning, deprovisioning, troubleshooting), see the [User Guide](docs/user-guide.md).

## Repo layout

```
.
├── bootstrap/          # Hub bootstrap (ArgoCD Application for hub-config)
├── hub-config/         # Hub operators: Tekton, cert-manager, Crossplane provider
├── tekton/             # Pipeline, Task, EventListener, Trigger definitions
├── clusters/           # One directory per cluster (spec, tier label, overrides)
├── cluster-templates/  # Kustomize bases for cluster specs (by tier)
├── workloads/          # Tier-specific day-2 overlays (base / virt / ai)
├── fleet/              # Python CLI tools for Tekton pipeline tasks
├── tests/              # Unit, validation, and fixture data
└── docs/               # Architecture, runbooks, diagrams
```

## Status

| Area | State |
|---|---|
| Architecture direction | ✅ Agreed |
| Repo structure | ✅ Done |
| Hub bootstrap (Tekton, cert-manager, Crossplane) | ✅ Done (manifests ready, not yet applied) |
| Development tooling (yamllint, tox, pytest) | ✅ Done |
| CI (GitHub Actions: gitleaks, tox, tekton-lint, kustomize) | ✅ Done |
| Container image build (multi-arch, quay.io/rhopl) | ✅ Done |
| Cluster templates (AWS HA base tier) | ✅ Done |
| Provision pipeline (13 tasks, triggers) | ✅ Done |
| Post-provision pipeline (base tier, 10 tasks, triggers) | ✅ Done |
| Post-provision pipeline (virt, ai tiers) | ⏳ Planned |
| Deprovision pipeline (4 tasks, triggers) | ✅ Done |
| Tekton triggers (provision, post-provision, deprovision) | ✅ Done |
| ApplicationSet day-2 delivery | ⏳ Planned |
| Migration from `labargocd` | ⏳ Planned |

## Background

This repo supersedes the cluster-lifecycle portions of [`labargocd`](https://github.com/redhat-openshift-partner-labs/labargocd). Architecture rationale and migration plan are in [`docs/architecture.md`](./docs/architecture.md).

## Contributing

Not open for contributions yet. Issues and discussion welcome as scaffolding lands.
