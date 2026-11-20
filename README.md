# fleet

> **Status:** 🚧 Early development. Architecture agreed; implementation in progress.

fleet is the control plane for the Red Hat OpenShift Partner Labs cluster fleet. It is for the lab operators who provision, configure and deprovision the OpenShift clusters delivered to partners.

## What lives here

This repository holds:

- the Tekton pipelines, tasks and triggers that run the cluster lifecycle
- the Python CLI tools that implement the Tekton tasks, built into one pipeline image
- the hub cluster configuration (operators, Crossplane, ArgoCD bootstrap)
- the tier workload overlays that the post-provision pipeline applies to a spoke

It does **not** hold cluster definitions or tenant application manifests. Cluster definitions live in [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters); a push to that repository triggers the pipelines defined here.

## Architecture at a glance

- **Git** — source of truth: pipelines and hub configuration in this repo, cluster definitions in fleet-clusters
- **Tekton** (OpenShift Pipelines) — workflow engine for pre-provision, provision, post-provision, and deprovision
- **ArgoCD** (OpenShift GitOps) — manifest delivery to the hub; day-2 workload delivery to spokes via `ApplicationSet` is planned
- **ACM + Hive** — fleet membership and cluster provisioning
- **cert-manager** — hub-side TLS certificate management; spokes receive only derived artifacts
- **Crossplane** — per-cluster IAM user generation; installed by `hub-config/crossplane/`

The guiding rule: *ArgoCD reconciles declarative state. Tekton runs ordered workflows. ACM/Hive controls cluster lifecycle.* Each tool does one job.

For day-to-day operations (provisioning, deprovisioning, troubleshooting), see the [User Guide](docs/user-guide.md).

## Pipelines

| Pipeline | Purpose | Tasks |
|---|---|---|
| [`pre-provision`](tekton/pipelines/pre-provision.yaml) | Creates the cluster namespace, SSH key, pull secret and IAM credentials, validates the cluster inputs, and starts `provision` | 14 |
| [`provision`](tekton/pipelines/provision.yaml) | Applies the cluster resources, waits for Hive and the ManagedCluster, reads the tier, and starts `post-provision` | 11 |
| [`post-provision`](tekton/pipelines/post-provision.yaml) | Configures OAuth, the TLS certificate and RBAC on the spoke, applies the tier workloads, and publishes the access details | 23 |
| [`deprovision`](tekton/pipelines/deprovision.yaml) | Terminates the pod VMs of a `coco` cluster, deletes the cluster, waits for the Hive uninstall, removes hub artifacts, and records the result | 7 |
| [`test-vcluster`](tekton/pipelines/test-vcluster.yaml) | Runs `post-provision` against a temporary vCluster on the hub | 5 |

## Tiers

The `tier` label on a ManagedCluster selects what the post-provision pipeline installs. Every tier includes `base`.

| Tier | Overlay | Installs |
|---|---|---|
| `base` | `workloads/base/` | Core configuration: OAuth, TLS certificate, RBAC, and the base overlay |
| `virt` | `workloads/virt/` | OpenShift Virtualization; Node Feature Discovery when the catalog provides it |
| `ai` | `workloads/ai/` | OpenShift AI 2.x or 3.x, for CPU or GPU |
| `coco` | `workloads/coco/` | OpenShift sandboxed containers with peer pods on AWS |

## Repo layout

```
.
├── bootstrap/          # Hub bootstrap (ArgoCD Application for hub-config)
├── hub-config/         # Hub operators: ACM, GitOps, Pipelines, cert-manager, RH-SSO, Crossplane
├── tekton/             # Pipeline, Task, EventListener, Trigger definitions
├── workloads/          # Tier-specific day-2 overlays (base / virt / ai / coco)
├── fleet/              # Python CLI tools for Tekton pipeline tasks
├── tests/              # Unit and validation tests
└── docs/               # Architecture, runbooks, diagrams
```

## Status

| Area | State |
|---|---|
| Architecture direction | ✅ Agreed |
| Repo structure | ✅ Done |
| Hub bootstrap (Tekton, cert-manager, Crossplane) | ✅ Done (manifests ready, not yet applied) |
| Development tooling (yamllint, tox, pytest) | ✅ Done |
| CI (GitHub Actions: gitleaks, tox, tekton-lint) | ✅ Done |
| Container image build (multi-arch, quay.io/rhopl) | ✅ Done |
| Pre-provision and provision pipelines | ✅ Done |
| Post-provision pipeline (base, virt, ai, coco tiers) | ✅ Done |
| Deprovision pipeline | ✅ Done |
| Tekton triggers (pre-provision, post-provision, deprovision) | ✅ Done |
| ApplicationSet day-2 delivery | ⏳ Planned |
| Migration from `labargocd` | ⏳ Planned |

CI does not run `tox -e validate-kustomize`; run it locally.

## Background

This repo supersedes the cluster-lifecycle portions of [`labargocd`](https://github.com/redhat-openshift-partner-labs/labargocd). Architecture rationale and migration plan are in [`docs/architecture.md`](./docs/architecture.md).

## Contributing

This repository does not accept external pull requests. Report bugs and request features through [GitHub issues](https://github.com/redhat-openshift-partner-labs/fleet/issues).
