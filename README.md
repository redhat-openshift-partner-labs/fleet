# fleet

[![CI](https://github.com/redhat-openshift-partner-labs/fleet/actions/workflows/ci.yml/badge.svg)](https://github.com/redhat-openshift-partner-labs/fleet/actions/workflows/ci.yml)
[![Image build](https://github.com/redhat-openshift-partner-labs/fleet/actions/workflows/build-image.yml/badge.svg)](https://github.com/redhat-openshift-partner-labs/fleet/actions/workflows/build-image.yml)
[![Release](https://img.shields.io/github/v/release/redhat-openshift-partner-labs/fleet)](https://github.com/redhat-openshift-partner-labs/fleet/releases/latest)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

fleet is the control plane for the Red Hat OpenShift Partner Labs cluster fleet. It is for the lab operators who provision, configure and deprovision the OpenShift clusters delivered to partners.

## Architecture

![Architecture](docs/diagrams/architecture.svg)

A push to the fleet-clusters repository starts a Tekton pipeline on the hub cluster. The pipelines create the AWS credentials of the cluster through Crossplane, install the cluster through Hive, register it in ACM, and configure it with a certificate from cert-manager and an OIDC client in Keycloak. ArgoCD syncs the hub configuration from this repository.

[docs/architecture.md](docs/architecture.md) describes each component, the trust boundary between the hub and a spoke, and the tasks of each pipeline. Diagram source: [docs/diagrams/architecture.mermaid](docs/diagrams/architecture.mermaid).

## What this repository holds

- The Tekton pipelines, tasks and triggers that run the cluster lifecycle
- The Python CLI tools that implement the Tekton tasks, built into one pipeline image
- The hub cluster configuration (operators, Crossplane, ArgoCD bootstrap)
- The tier workload overlays that the post-provision pipeline applies to a spoke

It does not hold cluster definitions or tenant application manifests. Cluster definitions live in [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters); a push to that repository triggers the pipelines defined here.

## Pipelines

| Pipeline | Purpose | Tasks |
|---|---|---|
| [`pre-provision`](tekton/pipelines/pre-provision.yaml) | Creates the cluster namespace, SSH key, pull secret and IAM credentials, validates the cluster inputs, and starts `provision` | 14 |
| [`provision`](tekton/pipelines/provision.yaml) | Applies the cluster resources, waits for Hive and the ManagedCluster, reads the tier, and starts `post-provision` | 11 |
| [`post-provision`](tekton/pipelines/post-provision.yaml) | Configures OAuth, the TLS certificate and RBAC on the spoke, applies the tier workloads, and publishes the access details | 23 |
| [`deprovision`](tekton/pipelines/deprovision.yaml) | Terminates the pod VMs of a `coco` cluster, deletes the cluster, waits for the Hive uninstall, removes hub artifacts, and records the result | 7 |
| [`test-vcluster`](tekton/pipelines/test-vcluster.yaml) | Runs `post-provision` against a temporary vCluster on the hub | 5 |

- Tasks: [docs/architecture.md](docs/architecture.md#pipelines) lists the tasks of each pipeline, with a flowchart and a sequence diagram.
- Tiers: the `tier` label of a cluster is `base`, `virt`, `ai` or `coco`, and selects the workloads that `post-provision` installs. See [Tiers](docs/user-guide.md#tiers).
- Not implemented: spoke certificate rotation and a deprovision approval gate. See [Not implemented](docs/architecture.md#not-implemented).

## Repository layout

```
.
├── bootstrap/          # ArgoCD Application that syncs hub-config/ to the hub
├── hub-config/         # Hub operators: ACM, GitOps, Pipelines, cert-manager, RH-SSO, Crossplane
├── tekton/             # Pipeline, Task, EventListener and Trigger definitions
├── workloads/          # Tier overlays that post-provision applies: base, virt, ai, coco
├── fleet/              # Python CLI tools that implement the Tekton tasks
├── tests/              # Unit tests of the CLI tools; validation tests of manifests and documents
├── docs/               # Documents and diagrams
├── Dockerfile          # Pipeline image; Containerfile is a symlink to it
├── pyproject.toml      # Package definition and CLI entry points
└── tox.ini             # Entry point of every check
```

## Documentation

Operators start with the user guide. Hub administrators start with the hub cluster setup. Contributors start with the developer guide.

| Document | Reader | Covers |
|---|---|---|
| [User guide](docs/user-guide.md) | Operators | The tasks an operator performs: provision a cluster, hand over access, monitor a run, deprovision a cluster, and recover from a failed task |
| [Architecture](docs/architecture.md) | Operators and contributors | The components of the system, the trust boundary, the trigger chain, the tasks of each pipeline, and the AWS credential modes |
| [Per-cluster metadata](docs/per-cluster-metadata.md) | Operators | The `metadata.yaml` keys and how their values reach the tasks |
| [Confidential containers tier](docs/coco-tier.md) | Operators | Prerequisites, limits and operation of `coco` clusters |
| [OpenShift AI operator mapping](docs/openshift-ai-operator-and-component-mapping.md) | Operators | Operators and components for OpenShift AI 2.x and 3.x |
| [Hub cluster setup](hub-config/README.md) | Hub administrators | Installing, verifying and uninstalling the hub operators |
| [fleet-clusters setup](docs/fleet-clusters-setup.md) | Hub administrators | Repository structure, GitHub App, webhook and archive workflow |
| [Image pull secret setup](docs/image-pull-secret-setup.md) | Hub administrators | Credentials for pulling the pipeline image from quay.io |
| [Developer guide](docs/developer-guide.md) | Contributors | Local setup, checks, adding a Tekton task, the pipeline image, documents and diagrams |
| [Parameter threading](docs/parameter-threading.md) | Contributors | How a parameter passes from a trigger to a task |
| [vCluster test infrastructure](docs/vcluster.md) | Contributors | Testing `post-provision` against a temporary vCluster |

## Development

Prerequisites: Python 3.11 or later and [Poetry](https://python-poetry.org/). The [developer guide](docs/developer-guide.md) lists the remaining tools.

```bash
poetry install
tox
```

| Check | Local command | Runs in CI |
|---|---|---|
| Unit and validation tests; 100% line coverage of `fleet/` | `tox` | Yes |
| `yamllint`, `black`, `mypy`, `pylint`, `bandit` | `tox` | Yes |
| `tekton-lint` | `tox -e tekton-lint` | Yes |
| `kustomize build` of the tier overlays | `tox -e validate-kustomize` | No |
| `gitleaks` | pre-commit hook | Yes |

CI runs on a push to any branch except `main` and on a pull request to `main`.

A tag that starts with `v` builds the pipeline image `quay.io/rhopl/fleet-pipeline` for `linux/amd64` and `linux/arm64` and creates the GitHub release.

## Contributing

This repository does not accept external pull requests. Report bugs and request features through [GitHub issues](https://github.com/redhat-openshift-partner-labs/fleet/issues).
