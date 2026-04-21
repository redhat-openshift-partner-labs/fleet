# Fleet Migration Plan: labargocd → fleet

## Context

The `labargocd` repo uses an ArgoCD app-of-apps pattern to orchestrate OpenShift cluster lifecycle (provision, post-provision SSL, deprovision). This works but has architectural problems: ArgoCD is a reconciler being used as a workflow engine, requiring compensators like PostSync polling Jobs, custom finalizers, and a cluster-wide 5-minute CronJob. The `fleet` repo replaces the workflow orchestration with Tekton pipelines while keeping ArgoCD for what it does well (hub manifest delivery, day-2 workload reconciliation via ApplicationSet).

**Key decisions made:**
- **AWS credentials**: Keep Crossplane per-cluster IAM user generation (each cluster retains its own AWS creds)
- **TLS**: Keep Let's Encrypt with per-cluster AWS credentials for Route53 DNS-01 validation
- **Scope**: Full implementation YAML for each phase

**Prerequisites**: Crossplane is pre-installed on the hub for per-cluster IAM user generation. It is not managed by this repo — only the Provider/ProviderConfig resources are carried over for ArgoCD to reconcile.

**Source repo**: `labargocd`
**Target repo**: `fleet`

---

## Phase 1: Repository Scaffolding + Hub Infrastructure

**Goal**: Create directory structure, bootstrap ArgoCD Application for hub infrastructure (Tekton, cert-manager). Crossplane Provider/ProviderConfig carried over.

**No cluster lifecycle changes. labargocd continues to manage all clusters.**

### Files to create

```
fleet/
├── bootstrap/
│   ├── kustomization.yaml
│   └── argocd-application-hub-config.yaml
├── hub-config/
│   ├── kustomization.yaml
│   ├── namespaces.yaml
│   ├── tekton/
│   │   ├── kustomization.yaml
│   │   └── subscription.yaml
│   ├── cert-manager/
│   │   ├── kustomization.yaml
│   │   └── subscription.yaml
│   └── crossplane/
│       ├── kustomization.yaml
│       ├── provider.yaml
│       └── providerconfig.yaml
├── tekton/
│   └── .gitkeep
├── clusters/
│   └── .gitkeep
├── workloads/
│   └── .gitkeep
├── cluster-templates/
│   └── .gitkeep
├── .yamllint
├── .tektonlintrc.yaml
├── .pre-commit-config.yaml
├── pyproject.toml
├── tox.ini
├── Makefile
├── Dockerfile              # Pipeline container image (Python tools + oc CLI)
├── fleet/                  # Python package (CLI tools for Tekton tasks)
│   ├── __init__.py
│   └── tasks/
│       └── __init__.py
└── tests/
    ├── conftest.py
    ├── unit/
    │   └── __init__.py
    └── validation/
        └── test_kustomize_build.py
```

### bootstrap/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - argocd-application-hub-config.yaml
```

### bootstrap/argocd-application-hub-config.yaml

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: fleet-hub-config
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://github.com/redhat-openshift-partner-labs/fleet.git
    targetRevision: main
    path: hub-config
  destination:
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

### hub-config/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespaces.yaml
  - tekton/
  - cert-manager/
  - crossplane/
```

### hub-config/namespaces.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-pipelines
---
apiVersion: v1
kind: Namespace
metadata:
  name: cert-manager
```

### hub-config/tekton/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - subscription.yaml
```

### hub-config/tekton/subscription.yaml

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-pipelines-operator
  namespace: openshift-operators
spec:
  channel: latest
  installPlanApproval: Automatic
  name: openshift-pipelines-operator-rh
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

### hub-config/cert-manager/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - subscription.yaml
```

### hub-config/cert-manager/subscription.yaml

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: cert-manager
  namespace: openshift-operators
spec:
  channel: stable
  installPlanApproval: Automatic
  name: cert-manager-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

### hub-config/crossplane/kustomization.yaml

Carry over from `labargocd/bootstrap/crossplane-provider.yaml`. The Provider and ProviderConfig are hub-level resources.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - provider.yaml
  - providerconfig.yaml
```

### hub-config/crossplane/provider.yaml

Carry over from labargocd — the Crossplane AWS Provider that enables per-cluster IAM resource creation.

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-aws-iam
spec:
  package: xpkg.upbound.io/upbound/provider-aws-iam:v1.20.0
  controllerConfigRef:
    name: provider-aws-iam
---
apiVersion: pkg.crossplane.io/v1alpha1
kind: ControllerConfig
metadata:
  name: provider-aws-iam
spec:
  securityContext:
    runAsNonRoot: true
```

### hub-config/crossplane/providerconfig.yaml

```yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-credentials
      key: credentials
```

### .yamllint

Based on operator-pipelines:

```yaml
extends: default

rules:
  line-length:
    max: 180

ignore: |
  .tox/
  .venv/
  tmp/
```

### .tektonlintrc.yaml

```yaml
rules:
  prefer-kebab-case: off
```

### .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

### pyproject.toml

Poetry-managed. Key settings:

```toml
[tool.poetry]
name = "fleet"
version = "0.1.0"
description = "CLI tools for fleet Tekton pipeline tasks"
packages = [{include = "fleet"}]

[tool.poetry.dependencies]
python = ">=3.11"
pyyaml = "^6.0"
kubernetes = "^29.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-cov = "^5.0"
tox = "^4.0"
yamllint = "^1.35"
black = "^24.0"
mypy = "^1.0"
pylint = "^3.0"
bandit = "^1.7"

[tool.poetry.scripts]
# Entry points added as tasks are built, e.g.:
# fleet-validate-inputs = "fleet.tasks.validate_inputs:main"
```

### tox.ini

```ini
[tox]
envlist = test, yamllint, black, mypy, pylint, bandit
skipsdist = false

[testenv:test]
commands = pytest -v --cov fleet --cov-report term-missing --cov-fail-under 100

[testenv:yamllint]
commands = yamllint -c .yamllint .

[testenv:tekton-lint]
allowlist_externals = npx
commands = npx tekton-lint tekton/

[testenv:validate-kustomize]
commands = pytest tests/validation/

[testenv:black]
commands = black --check fleet/ tests/

[testenv:mypy]
commands = mypy fleet/

[testenv:pylint]
commands = pylint fleet/

[testenv:bandit]
commands = bandit -r fleet/
```

### Makefile

```makefile
.PHONY: lint lint-yaml lint-tekton validate

lint:
	tox

lint-yaml:
	tox -e yamllint

lint-tekton:
	tox -e tekton-lint

validate:
	tox -e validate-kustomize
```

### Dockerfile

Pipeline container image — built with Python tools + oc CLI. Placeholder for Phase 1, fleshed out as tasks are added.

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest

COPY . /src
RUN pip install /src

# oc CLI installed from OpenShift mirror
RUN curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /usr/local/bin oc kubectl
```

### tests/validation/test_kustomize_build.py

```python
import subprocess
from pathlib import Path

import pytest


def discover_kustomize_dirs():
    return sorted(Path("clusters").glob("*/kustomization.yaml"))


@pytest.mark.parametrize("kustomization", discover_kustomize_dirs(), ids=str)
def test_kustomize_build(kustomization):
    result = subprocess.run(
        ["kustomize", "build", str(kustomization.parent)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
```

### Acceptance criteria

- [ ] Tekton Pipelines operator running (`oc get csv -n openshift-operators | grep pipelines`)
- [ ] cert-manager operator running (`oc get csv -n openshift-operators | grep cert-manager`)
- [ ] Crossplane Provider healthy (`oc get provider.pkg`)
- [ ] ArgoCD Application `fleet-hub-config` synced and healthy
- [ ] `tox` passes (yamllint, tekton-lint)
- [ ] pre-commit hooks installed and gitleaks runs on push
- [ ] `tests/` directory exists with validation scaffolding
- [ ] `make lint` works

### Rollback

Delete `fleet-hub-config` Application from ArgoCD. All hub infra installed by this phase is removed by ArgoCD prune.

---

## Phase 2: Cluster Templates + Provision Pipeline (base tier)

**Goal**: Port cluster template from labargocd, build provision pipeline with Crossplane credential generation, test on one new cluster.

> **Python CLI pattern (applies to all phases with Tekton tasks):**
> - Each Tekton task's `script:` field is a thin bash stub calling a Python CLI entry point (e.g., `fleet-validate-inputs`)
> - Python source lives in `fleet/tasks/` and is tested via `tests/unit/`
> - The inline bash task bodies shown below will be reimplemented as Python CLI tools during implementation
> - The Tekton Task YAML structure (params, workspaces, results) stays the same — only the script content changes

### Files to create

```
fleet/
├── cluster-templates/
│   └── aws-ha/
│       └── base/
│           ├── kustomization.yaml
│           ├── namespace.yaml
│           ├── clusterdeployment.yaml
│           ├── machinepool-worker.yaml
│           ├── managedcluster.yaml
│           ├── install-config-secret.yaml
│           └── crossplane/
│               ├── kustomization.yaml
│               ├── iam-user.yaml
│               ├── iam-policy.yaml
│               ├── iam-attachment.yaml
│               ├── iam-access-key.yaml
│               └── credentials-transformer-job.yaml
├── clusters/
│   └── test-cluster-01/
│       ├── kustomization.yaml
│       ├── argocd-application.yaml      # NOT used by pipeline; kept for format compat
│       └── patches/
│           └── install-config.yaml
├── tekton/
│   ├── kustomization.yaml
│   ├── rbac/
│   │   ├── kustomization.yaml
│   │   ├── serviceaccount.yaml
│   │   ├── clusterrole.yaml
│   │   └── clusterrolebinding.yaml
│   ├── tasks/
│   │   ├── kustomization.yaml
│   │   ├── create-cluster-namespace.yaml
│   │   ├── apply-crossplane-credentials.yaml
│   │   ├── wait-for-aws-credentials.yaml
│   │   ├── validate-cluster-inputs.yaml
│   │   ├── apply-cluster-crs.yaml
│   │   ├── wait-for-hive-ready.yaml
│   │   ├── wait-for-managed-cluster.yaml
│   │   ├── extract-spoke-kubeconfig.yaml
│   │   └── label-for-post-provision.yaml
│   ├── pipelines/
│   │   ├── kustomization.yaml
│   │   └── provision.yaml
│   └── triggers/
│       ├── kustomization.yaml
│       ├── eventlistener.yaml
│       ├── triggerbinding-provision.yaml
│       └── triggertemplate-provision.yaml
```

### cluster-templates/aws-ha/base/kustomization.yaml

Carried over from `labargocd/cluster-templates/aws-ha/base/kustomization.yaml`. The Crossplane resources and credentials transformer are included.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespace.yaml
  - crossplane/iam-user.yaml
  - crossplane/iam-policy.yaml
  - crossplane/iam-attachment.yaml
  - crossplane/iam-access-key.yaml
  - crossplane/credentials-transformer-job.yaml
  - install-config-secret.yaml
  - clusterdeployment.yaml
  - machinepool-worker.yaml
  - managedcluster.yaml
```

### cluster-templates/aws-ha/base/namespace.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: cluster-placeholder
```

### cluster-templates/aws-ha/base/clusterdeployment.yaml

Carried over from labargocd. Sync-wave annotations removed (Tekton controls ordering).

```yaml
apiVersion: hive.openshift.io/v1
kind: ClusterDeployment
metadata:
  name: cluster-placeholder
  namespace: cluster-placeholder
spec:
  baseDomain: openshiftpartnerlabs.com
  clusterName: cluster-placeholder
  platform:
    aws:
      credentialsSecretRef:
        name: aws-credentials
      region: us-east-1
  provisioning:
    installConfigSecretRef:
      name: cluster-placeholder-install-config
    sshPrivateKeySecretRef:
      name: cluster-placeholder-ssh-key
    imageSetRef:
      name: img4.20.10-x86-64-appsub
  pullSecretRef:
    name: pull-secret
  powerState: Running
```

### cluster-templates/aws-ha/base/machinepool-worker.yaml

```yaml
apiVersion: hive.openshift.io/v1
kind: MachinePool
metadata:
  name: cluster-placeholder-worker
  namespace: cluster-placeholder
spec:
  clusterDeploymentRef:
    name: cluster-placeholder
  name: worker
  platform:
    aws:
      rootVolume:
        iops: 4000
        size: 100
        type: gp3
      type: m5.2xlarge
      zones:
        - us-east-1a
        - us-east-1b
        - us-east-1c
  replicas: 3
  labels:
    node-role.kubernetes.io/worker: ""
```

### cluster-templates/aws-ha/base/managedcluster.yaml

Contains both ManagedCluster and KlusterletAddonConfig (same as labargocd).

```yaml
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: cluster-placeholder
  labels:
    cloud: AWS
    vendor: OpenShift
    environment: production
    cluster.open-cluster-management.io/clusterset: default
spec:
  hubAcceptsClient: true
  leaseDurationSeconds: 60
---
apiVersion: agent.open-cluster-management.io/v1
kind: KlusterletAddonConfig
metadata:
  name: cluster-placeholder
  namespace: cluster-placeholder
spec:
  clusterName: cluster-placeholder
  clusterNamespace: cluster-placeholder
  clusterLabels:
    cloud: AWS
    vendor: OpenShift
  applicationManager:
    enabled: true
  policyController:
    enabled: true
  searchCollector:
    enabled: true
  certPolicyController:
    enabled: true
```

### cluster-templates/aws-ha/base/install-config-secret.yaml

Carried over from labargocd. Full install-config template.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cluster-placeholder-install-config
  namespace: cluster-placeholder
type: Opaque
stringData:
  install-config.yaml: |
    apiVersion: v1
    baseDomain: openshiftpartnerlabs.com
    metadata:
      name: cluster-placeholder
    controlPlane:
      name: master
      platform:
        aws:
          type: m8i.2xlarge
          zones:
            - us-east-1a
            - us-east-1b
            - us-east-1c
      replicas: 3
    compute:
      - name: worker
        platform:
          aws:
            rootVolume:
              iops: 4000
              size: 100
              type: gp3
            type: m8i.2xlarge
            zones:
              - us-east-1a
              - us-east-1b
              - us-east-1c
        replicas: 3
    networking:
      clusterNetwork:
        - cidr: 10.128.0.0/14
          hostPrefix: 23
      machineNetwork:
        - cidr: 10.0.0.0/16
      serviceNetwork:
        - 172.30.0.0/16
      networkType: OVNKubernetes
    platform:
      aws:
        region: us-east-1
    publish: External
```

### cluster-templates/aws-ha/base/crossplane/ (all files)

Carried over from `labargocd/cluster-templates/aws-ha/base/crossplane/`. Sync-wave annotations removed.

**crossplane/kustomization.yaml**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - iam-user.yaml
  - iam-policy.yaml
  - iam-attachment.yaml
  - iam-access-key.yaml
  - credentials-transformer-job.yaml
```

**crossplane/iam-user.yaml**
```yaml
apiVersion: iam.aws.upbound.io/v1beta1
kind: User
metadata:
  name: cluster-placeholder-ocp-installer
  namespace: cluster-placeholder
spec:
  forProvider: {}
  providerConfigRef:
    name: default
```

**crossplane/iam-policy.yaml**
```yaml
apiVersion: iam.aws.upbound.io/v1beta1
kind: Policy
metadata:
  name: cluster-placeholder-openshift4installerpolicy
  namespace: cluster-placeholder
spec:
  forProvider:
    name: cluster-placeholder-OpenShift4InstallerPolicy
    policy: |
      {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "ec2:*",
              "elasticloadbalancing:*",
              "iam:*",
              "route53:*",
              "s3:*",
              "sts:*",
              "tag:*",
              "cloudformation:*",
              "autoscaling:*",
              "servicequotas:*"
            ],
            "Resource": "*"
          }
        ]
      }
  providerConfigRef:
    name: default
```

**crossplane/iam-attachment.yaml**
```yaml
apiVersion: iam.aws.upbound.io/v1beta1
kind: UserPolicyAttachment
metadata:
  name: cluster-placeholder-policy-attachment
  namespace: cluster-placeholder
spec:
  forProvider:
    policyArnRef:
      name: cluster-placeholder-openshift4installerpolicy
    userRef:
      name: cluster-placeholder-ocp-installer
  providerConfigRef:
    name: default
```

**crossplane/iam-access-key.yaml**
```yaml
apiVersion: iam.aws.upbound.io/v1beta1
kind: AccessKey
metadata:
  name: cluster-placeholder-access-key
  namespace: cluster-placeholder
spec:
  forProvider:
    userRef:
      name: cluster-placeholder-ocp-installer
  providerConfigRef:
    name: default
  writeConnectionSecretToRef:
    name: aws-credentials-raw
    namespace: cluster-placeholder
```

**crossplane/credentials-transformer-job.yaml**

Transforms Crossplane's `aws-credentials-raw` (keys: `username`, `password`) into Hive-compatible `aws-credentials` (keys: `aws_access_key_id`, `aws_secret_access_key`).

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: cluster-placeholder-credentials-transformer
  namespace: cluster-placeholder
spec:
  backoffLimit: 6
  activeDeadlineSeconds: 600
  template:
    spec:
      serviceAccountName: credentials-transformer-sa
      restartPolicy: OnFailure
      containers:
        - name: transform
          image: registry.redhat.io/openshift4/ose-cli:v4.14
          command:
            - /bin/bash
            - -c
            - |
              set -euo pipefail
              NAMESPACE="cluster-placeholder"
              RAW_SECRET="aws-credentials-raw"
              TARGET_SECRET="aws-credentials"

              echo "Waiting for Crossplane to create $RAW_SECRET..."
              until oc get secret "$RAW_SECRET" -n "$NAMESPACE" 2>/dev/null; do
                sleep 5
              done

              ACCESS_KEY=$(oc get secret "$RAW_SECRET" -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 -d)
              SECRET_KEY=$(oc get secret "$RAW_SECRET" -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 -d)

              oc create secret generic "$TARGET_SECRET" \
                -n "$NAMESPACE" \
                --from-literal=aws_access_key_id="$ACCESS_KEY" \
                --from-literal=aws_secret_access_key="$SECRET_KEY" \
                --dry-run=client -o yaml | oc apply -f -

              echo "AWS credentials transformed successfully"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: credentials-transformer-sa
  namespace: cluster-placeholder
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: credentials-transformer
  namespace: cluster-placeholder
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: credentials-transformer
  namespace: cluster-placeholder
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: credentials-transformer
subjects:
  - kind: ServiceAccount
    name: credentials-transformer-sa
    namespace: cluster-placeholder
```

### clusters/test-cluster-01/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: test-cluster-01

resources:
  - ../../cluster-templates/aws-ha/base

patches:
  - path: patches/install-config.yaml
  - target:
      kind: Namespace
      name: cluster-placeholder
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01
  - target:
      kind: ClusterDeployment
      name: cluster-placeholder
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
      - op: replace
        path: /spec/clusterName
        value: test-cluster-01
      - op: replace
        path: /spec/provisioning/installConfigSecretRef/name
        value: test-cluster-01-install-config
      - op: replace
        path: /spec/provisioning/sshPrivateKeySecretRef/name
        value: test-cluster-01-ssh-key
  - target:
      kind: MachinePool
      name: cluster-placeholder-worker
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-worker
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
      - op: replace
        path: /spec/clusterDeploymentRef/name
        value: test-cluster-01
  - target:
      kind: ManagedCluster
      name: cluster-placeholder
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01
      - op: add
        path: /metadata/labels/tier
        value: base
      - op: add
        path: /metadata/labels/environment
        value: development
  - target:
      kind: KlusterletAddonConfig
      name: cluster-placeholder
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
      - op: replace
        path: /spec/clusterName
        value: test-cluster-01
      - op: replace
        path: /spec/clusterNamespace
        value: test-cluster-01
  - target:
      kind: Secret
      name: cluster-placeholder-install-config
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-install-config
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
  - target:
      kind: User
      name: cluster-placeholder-ocp-installer
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-ocp-installer
  - target:
      kind: Policy
      name: cluster-placeholder-openshift4installerpolicy
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-openshift4installerpolicy
      - op: replace
        path: /spec/forProvider/name
        value: test-cluster-01-OpenShift4InstallerPolicy
  - target:
      kind: UserPolicyAttachment
      name: cluster-placeholder-policy-attachment
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-policy-attachment
      - op: replace
        path: /spec/forProvider/policyArnRef/name
        value: test-cluster-01-openshift4installerpolicy
      - op: replace
        path: /spec/forProvider/userRef/name
        value: test-cluster-01-ocp-installer
  - target:
      kind: AccessKey
      name: cluster-placeholder-access-key
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-access-key
      - op: replace
        path: /spec/forProvider/userRef/name
        value: test-cluster-01-ocp-installer
      - op: replace
        path: /spec/writeConnectionSecretToRef/namespace
        value: test-cluster-01
  - target:
      kind: Job
      name: cluster-placeholder-credentials-transformer
    patch: |
      - op: replace
        path: /metadata/name
        value: test-cluster-01-credentials-transformer
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
  - target:
      kind: ServiceAccount
      name: credentials-transformer-sa
    patch: |
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
  - target:
      kind: Role
      name: credentials-transformer
    patch: |
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
  - target:
      kind: RoleBinding
      name: credentials-transformer
    patch: |
      - op: replace
        path: /metadata/namespace
        value: test-cluster-01
      - op: replace
        path: /subjects/0/namespace
        value: test-cluster-01
```

### clusters/test-cluster-01/patches/install-config.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: test-cluster-01-install-config
  namespace: test-cluster-01
type: Opaque
stringData:
  install-config.yaml: |
    apiVersion: v1
    baseDomain: openshiftpartnerlabs.com
    metadata:
      name: test-cluster-01
    controlPlane:
      name: master
      platform:
        aws:
          type: m8i.2xlarge
          zones:
            - us-east-1a
            - us-east-1b
            - us-east-1c
      replicas: 3
    compute:
      - name: worker
        platform:
          aws:
            rootVolume:
              iops: 4000
              size: 100
              type: gp3
            type: m8i.2xlarge
            zones:
              - us-east-1a
              - us-east-1b
              - us-east-1c
        replicas: 3
    networking:
      clusterNetwork:
        - cidr: 10.128.0.0/14
          hostPrefix: 23
      machineNetwork:
        - cidr: 10.0.0.0/16
      serviceNetwork:
        - 172.30.0.0/16
      networkType: OVNKubernetes
    platform:
      aws:
        region: us-east-1
    publish: External
```

### tekton/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - rbac/
  - tasks/
  - pipelines/
  - triggers/
```

### tekton/rbac/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - serviceaccount.yaml
  - clusterrole.yaml
  - clusterrolebinding.yaml
```

### tekton/rbac/serviceaccount.yaml

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fleet-pipeline
  namespace: openshift-pipelines
```

### tekton/rbac/clusterrole.yaml

Scoped to minimum required permissions. Secrets get read + create/update (no delete — namespace
deletion handles secret cleanup during deprovision). Namespace-scoped RBAC (roles, rolebindings)
is separated from cluster-scoped RBAC (clusterroles, clusterrolebindings are not managed by
the pipeline and are excluded).

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: fleet-pipeline
rules:
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list", "watch", "create", "delete"]
  - apiGroups: [""]
    resources: ["secrets", "serviceaccounts", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create"]
  - apiGroups: ["batch"]
    resources: ["jobs"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["roles", "rolebindings"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["hive.openshift.io"]
    resources: ["clusterdeployments", "machinepools"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["cluster.open-cluster-management.io"]
    resources: ["managedclusters"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["agent.open-cluster-management.io"]
    resources: ["klusterletaddonconfigs"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["iam.aws.upbound.io"]
    resources: ["users", "policies", "userpolicyattachments", "accesskeys"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["cert-manager.io"]
    resources: ["certificates"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["cert-manager.io"]
    resources: ["clusterissuers"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
  - apiGroups: ["tekton.dev"]
    resources: ["pipelineruns"]
    verbs: ["create"]
```

### tekton/rbac/clusterrolebinding.yaml

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: fleet-pipeline
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: fleet-pipeline
subjects:
  - kind: ServiceAccount
    name: fleet-pipeline
    namespace: openshift-pipelines
```

### tekton/tasks/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - create-cluster-namespace.yaml
  - apply-crossplane-credentials.yaml
  - wait-for-aws-credentials.yaml
  - validate-cluster-inputs.yaml
  - apply-cluster-crs.yaml
  - wait-for-hive-ready.yaml
  - wait-for-managed-cluster.yaml
  - extract-spoke-kubeconfig.yaml
  - label-for-post-provision.yaml
```

### tekton/tasks/create-cluster-namespace.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: create-cluster-namespace
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: create-namespace
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        if oc get namespace "$CLUSTER" 2>/dev/null; then
          echo "Namespace $CLUSTER already exists"
        else
          oc create namespace "$CLUSTER"
          echo "Namespace $CLUSTER created"
        fi
```

### tekton/tasks/apply-crossplane-credentials.yaml

Applies Crossplane IAM resources (User, Policy, Attachment, AccessKey) and the credentials transformer Job into the cluster namespace. Uses kustomize build of the cluster directory to extract only the Crossplane resources.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-crossplane-credentials
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: git-repo-url
      type: string
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: source
  steps:
    - name: clone-and-apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        cd /workspace/source
        git clone --depth 1 --branch "$(params.git-revision)" "$(params.git-repo-url)" repo 2>/dev/null || \
          git clone --depth 1 "$(params.git-repo-url)" repo
        cd repo

        echo "Building kustomize output for clusters/$CLUSTER..."
        kustomize build "clusters/$CLUSTER" > /tmp/all-resources.yaml

        echo "Applying Crossplane IAM resources..."
        grep -A 1000 'kind: User' /tmp/all-resources.yaml | \
          awk '/^---/{exit}1' | oc apply -f - || true
        
        oc apply -f /tmp/all-resources.yaml \
          --selector='app.kubernetes.io/managed-by!=Helm' \
          --prune=false 2>/dev/null || \
        oc apply -f <(kustomize build "clusters/$CLUSTER")

        echo "Crossplane resources applied for $CLUSTER"
```

### tekton/tasks/wait-for-aws-credentials.yaml

Waits for the Crossplane credential flow to complete: IAM User created -> AccessKey generated -> credentials-transformer Job converts to Hive format.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: wait-for-aws-credentials
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: timeout-seconds
      type: string
      default: "600"
  steps:
    - name: wait
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        TIMEOUT="$(params.timeout-seconds)"
        ELAPSED=0

        echo "Waiting for aws-credentials Secret in namespace $CLUSTER..."
        echo "Crossplane will create IAM user, generate access key, and transformer Job will produce aws-credentials."

        until oc get secret aws-credentials -n "$CLUSTER" 2>/dev/null; do
          if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
            echo "ERROR: Timed out after ${TIMEOUT}s waiting for aws-credentials"
            echo "Check Crossplane resources and credentials-transformer Job:"
            oc get user.iam,accesskey.iam,job -n "$CLUSTER" 2>/dev/null || true
            exit 1
          fi
          sleep 10
          ELAPSED=$((ELAPSED + 10))
          echo "  waiting... (${ELAPSED}s / ${TIMEOUT}s)"
        done

        echo "aws-credentials Secret found in $CLUSTER"
```

### tekton/tasks/validate-cluster-inputs.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: validate-cluster-inputs
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: validate
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        ERRORS=0

        echo "Validating inputs for cluster $CLUSTER..."

        for SECRET in aws-credentials pull-secret "${CLUSTER}-ssh-key"; do
          if oc get secret "$SECRET" -n "$CLUSTER" 2>/dev/null; then
            echo "  OK Secret $SECRET exists"
          else
            echo "  MISSING Secret $SECRET"
            ERRORS=$((ERRORS + 1))
          fi
        done

        if oc get secret "${CLUSTER}-install-config" -n "$CLUSTER" 2>/dev/null; then
          echo "  OK install-config Secret exists"
        else
          echo "  MISSING install-config Secret"
          ERRORS=$((ERRORS + 1))
        fi

        if [ "$ERRORS" -gt 0 ]; then
          echo "ERROR: $ERRORS required secrets missing"
          exit 1
        fi

        echo "All inputs validated"
```

### tekton/tasks/apply-cluster-crs.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-cluster-crs
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: git-repo-url
      type: string
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: source
  steps:
    - name: apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        cd /workspace/source
        if [ ! -d repo ]; then
          git clone --depth 1 --branch "$(params.git-revision)" "$(params.git-repo-url)" repo 2>/dev/null || \
            git clone --depth 1 "$(params.git-repo-url)" repo
        fi
        cd repo

        echo "Applying cluster CRs for $CLUSTER..."
        kustomize build "clusters/$CLUSTER" | oc apply -f -

        echo "Cluster resources applied"
```

### tekton/tasks/wait-for-hive-ready.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: wait-for-hive-ready
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: timeout
      type: string
      default: "60m"
  steps:
    - name: wait
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Waiting for ClusterDeployment $CLUSTER to be provisioned (timeout: $(params.timeout))..."
        oc wait --for=condition=Provisioned \
          clusterdeployment/"$CLUSTER" \
          -n "$CLUSTER" \
          --timeout="$(params.timeout)"

        echo "Cluster $CLUSTER provisioned successfully"
```

### tekton/tasks/wait-for-managed-cluster.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: wait-for-managed-cluster
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: timeout
      type: string
      default: "15m"
  steps:
    - name: wait
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Waiting for ManagedCluster $CLUSTER to join (timeout: $(params.timeout))..."
        oc wait --for=condition=ManagedClusterJoined \
          managedcluster/"$CLUSTER" \
          --timeout="$(params.timeout)"

        echo "ManagedCluster $CLUSTER joined"
```

### tekton/tasks/extract-spoke-kubeconfig.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: extract-spoke-kubeconfig
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  workspaces:
    - name: shared
  steps:
    - name: extract
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Extracting spoke kubeconfig for $CLUSTER..."

        KUBECONFIG_SECRET=$(oc get clusterdeployment "$CLUSTER" -n "$CLUSTER" \
          -o jsonpath='{.spec.clusterMetadata.adminKubeconfigSecretRef.name}' 2>/dev/null || \
          echo "${CLUSTER}-admin-kubeconfig")

        oc extract secret/"$KUBECONFIG_SECRET" \
          -n "$CLUSTER" \
          --to=/workspace/shared \
          --keys=kubeconfig \
          --confirm

        echo "Spoke kubeconfig saved to workspace"
```

### tekton/tasks/label-for-post-provision.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: label-for-post-provision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: label
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        oc label managedcluster/"$CLUSTER" \
          provisioned=true \
          --overwrite

        echo "ManagedCluster $CLUSTER labeled provisioned=true"
```

### tekton/pipelines/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - provision.yaml
```

### tekton/pipelines/provision.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: provision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: tier
      type: string
      default: base
    - name: region
      type: string
      default: us-east-1
    - name: git-repo-url
      type: string
      default: https://github.com/redhat-openshift-partner-labs/fleet.git
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: shared-workspace

  tasks:
    - name: create-cluster-namespace
      taskRef:
        name: create-cluster-namespace
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: apply-crossplane-credentials
      taskRef:
        name: apply-crossplane-credentials
      runAfter:
        - create-cluster-namespace
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
      workspaces:
        - name: source
          workspace: shared-workspace

    - name: wait-for-aws-credentials
      taskRef:
        name: wait-for-aws-credentials
      runAfter:
        - apply-crossplane-credentials
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: validate-cluster-inputs
      taskRef:
        name: validate-cluster-inputs
      runAfter:
        - wait-for-aws-credentials
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: apply-cluster-crs
      taskRef:
        name: apply-cluster-crs
      runAfter:
        - validate-cluster-inputs
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
      workspaces:
        - name: source
          workspace: shared-workspace

    - name: wait-for-hive-ready
      taskRef:
        name: wait-for-hive-ready
      runAfter:
        - apply-cluster-crs
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      timeout: "1h15m"

    - name: wait-for-managed-cluster
      taskRef:
        name: wait-for-managed-cluster
      runAfter:
        - wait-for-hive-ready
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: extract-spoke-kubeconfig
      taskRef:
        name: extract-spoke-kubeconfig
      runAfter:
        - wait-for-managed-cluster
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: label-for-post-provision
      taskRef:
        name: label-for-post-provision
      runAfter:
        - extract-spoke-kubeconfig
      params:
        - name: cluster-name
          value: $(params.cluster-name)
```

### tekton/triggers/kustomization.yaml

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - eventlistener.yaml
  - triggerbinding-provision.yaml
  - triggertemplate-provision.yaml
  - triggerbinding-deprovision.yaml
  - triggertemplate-deprovision.yaml
```

### tekton/triggers/eventlistener.yaml

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: EventListener
metadata:
  name: fleet-cluster-lifecycle
  namespace: openshift-pipelines
spec:
  serviceAccountName: fleet-pipeline
  triggers:
    - name: provision
      interceptors:
        - ref:
            name: github
          params:
            - name: eventTypes
              value: ["push"]
        - ref:
            name: cel
          params:
            - name: filter
              value: >-
                body.ref == 'refs/heads/main' &&
                body.commits.exists(c, c.added.exists(f, f.startsWith('clusters/')))
            - name: overlays
              value:
                - key: cluster_name
                  expression: >-
                    body.commits.map(c, c.added.filter(f, f.startsWith('clusters/')))
                    .flatten()
                    .map(f, f.split('/')[1])
                    .filter(n, n != '')
                    [0]
      bindings:
        - ref: provision-binding
      template:
        ref: provision-template
    - name: deprovision
      interceptors:
        - ref:
            name: github
          params:
            - name: eventTypes
              value: ["push"]
        - ref:
            name: cel
          params:
            - name: filter
              value: >-
                body.ref == 'refs/heads/main' &&
                body.commits.exists(c, c.removed.exists(f, f.startsWith('clusters/')))
            - name: overlays
              value:
                - key: cluster_name
                  expression: >-
                    body.commits.map(c, c.removed.filter(f, f.startsWith('clusters/')))
                    .flatten()
                    .map(f, f.split('/')[1])
                    .filter(n, n != '')
                    [0]
      bindings:
        - ref: deprovision-binding
      template:
        ref: deprovision-template
```

### tekton/triggers/triggerbinding-provision.yaml

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerBinding
metadata:
  name: provision-binding
  namespace: openshift-pipelines
spec:
  params:
    - name: git-repo-url
      value: $(body.repository.clone_url)
    - name: git-revision
      value: $(body.after)
    - name: cluster-name
      value: $(extensions.cluster_name)
```

### tekton/triggers/triggertemplate-provision.yaml

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: provision-template
  namespace: openshift-pipelines
spec:
  params:
    - name: git-repo-url
    - name: git-revision
    - name: cluster-name
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: provision-$(tt.params.cluster-name)-
        namespace: openshift-pipelines
      spec:
        pipelineRef:
          name: provision
        params:
          - name: cluster-name
            value: $(tt.params.cluster-name)
          - name: git-repo-url
            value: $(tt.params.git-repo-url)
          - name: git-revision
            value: $(tt.params.git-revision)
        workspaces:
          - name: shared-workspace
            emptyDir: {}
        serviceAccountName: fleet-pipeline
```

### tekton/triggers/triggerbinding-deprovision.yaml

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerBinding
metadata:
  name: deprovision-binding
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      value: $(extensions.cluster_name)
```

### tekton/triggers/triggertemplate-deprovision.yaml

```yaml
apiVersion: triggers.tekton.dev/v1beta1
kind: TriggerTemplate
metadata:
  name: deprovision-template
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
  resourcetemplates:
    - apiVersion: tekton.dev/v1
      kind: PipelineRun
      metadata:
        generateName: deprovision-$(tt.params.cluster-name)-
        namespace: openshift-pipelines
      spec:
        pipelineRef:
          name: deprovision
        params:
          - name: cluster-name
            value: $(tt.params.cluster-name)
        serviceAccountName: fleet-pipeline
```

### Acceptance criteria

- [ ] `kustomize build clusters/test-cluster-01/` produces valid YAML
- [ ] Provision pipeline deploys and runs (`tkn pipeline start provision`)
- [ ] Crossplane creates IAM user + credentials-transformer produces `aws-credentials`
- [ ] ClusterDeployment reaches Provisioned=True
- [ ] ManagedCluster joins hub
- [ ] Spoke kubeconfig extracted to workspace
### Rollback

Delete fleet cluster definition. If cluster was partially provisioned, manually clean up with `oc delete clusterdeployment -n test-cluster-01 test-cluster-01`.

---

## Phase 3: Deprovision Pipeline

**Goal**: Build deprovision pipeline. Test full lifecycle (provision -> deprovision) on test cluster. Prove finalizers and CronJob are unnecessary.

### Files to create

```
fleet/tekton/
├── tasks/
│   ├── delete-cluster-resources.yaml
│   ├── wait-hive-uninstall.yaml
│   ├── cleanup-hub-artifacts.yaml
│   └── verify-deprovision.yaml
└── pipelines/
    └── deprovision.yaml
```

### tekton/tasks/delete-cluster-resources.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: delete-cluster-resources
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: delete
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Deleting cluster resources for $CLUSTER in explicit order..."

        oc delete klusterletaddonconfig "$CLUSTER" -n "$CLUSTER" --ignore-not-found=true
        echo "  KlusterletAddonConfig deleted"

        oc delete managedcluster "$CLUSTER" --ignore-not-found=true
        oc wait --for=delete managedcluster/"$CLUSTER" --timeout=5m 2>/dev/null || true
        echo "  ManagedCluster deleted"

        oc delete machinepool -n "$CLUSTER" --all --ignore-not-found=true
        echo "  MachinePools deleted"

        oc delete clusterdeployment "$CLUSTER" -n "$CLUSTER" --ignore-not-found=true
        echo "  ClusterDeployment delete requested (Hive uninstall will run)"
```

### tekton/tasks/wait-hive-uninstall.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: wait-hive-uninstall
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: timeout
      type: string
      default: "25m"
  steps:
    - name: wait
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Waiting for Hive uninstall to complete (timeout: $(params.timeout))..."
        echo "Hive will delete AWS resources (EC2, LBs, Route53, VPC, S3, EBS, IAM)."

        if oc get clusterdeployment "$CLUSTER" -n "$CLUSTER" 2>/dev/null; then
          oc wait --for=delete \
            clusterdeployment/"$CLUSTER" \
            -n "$CLUSTER" \
            --timeout="$(params.timeout)"
          echo "ClusterDeployment $CLUSTER deleted (cloud cleanup complete)"
        else
          echo "ClusterDeployment $CLUSTER already gone"
        fi
```

### tekton/tasks/cleanup-hub-artifacts.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: cleanup-hub-artifacts
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: cleanup
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Cleaning up hub-side artifacts for $CLUSTER..."

        oc delete certificate -n "$CLUSTER" --all --ignore-not-found=true 2>/dev/null || true
        echo "  Certificate CRs deleted"

        oc delete clusterissuer "letsencrypt-${CLUSTER}" --ignore-not-found=true 2>/dev/null || true
        echo "  ClusterIssuer deleted"

        oc delete user.iam -n "$CLUSTER" --all --ignore-not-found=true 2>/dev/null || true
        oc delete policy.iam -n "$CLUSTER" --all --ignore-not-found=true 2>/dev/null || true
        oc delete userpolicyattachment.iam -n "$CLUSTER" --all --ignore-not-found=true 2>/dev/null || true
        oc delete accesskey.iam -n "$CLUSTER" --all --ignore-not-found=true 2>/dev/null || true
        echo "  Crossplane IAM resources deleted"

        echo "Waiting for Crossplane resources to be fully cleaned up..."
        sleep 15

        oc delete namespace "$CLUSTER" --ignore-not-found=true
        echo "  Namespace $CLUSTER deleted (takes remaining secrets with it)"

        echo "Hub artifacts cleaned up"
```

### tekton/tasks/verify-deprovision.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: verify-deprovision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: verify
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        ERRORS=0

        echo "Verifying clean deprovision for $CLUSTER..."

        if oc get namespace "$CLUSTER" 2>/dev/null; then
          echo "  FAIL Namespace $CLUSTER still exists"
          ERRORS=$((ERRORS + 1))
        else
          echo "  OK Namespace $CLUSTER gone"
        fi

        if oc get managedcluster "$CLUSTER" 2>/dev/null; then
          echo "  FAIL ManagedCluster $CLUSTER still exists"
          ERRORS=$((ERRORS + 1))
        else
          echo "  OK ManagedCluster $CLUSTER gone"
        fi

        if oc get clusterdeployment "$CLUSTER" -n "$CLUSTER" 2>/dev/null; then
          echo "  FAIL ClusterDeployment $CLUSTER still exists"
          ERRORS=$((ERRORS + 1))
        else
          echo "  OK ClusterDeployment $CLUSTER gone"
        fi

        if [ "$ERRORS" -gt 0 ]; then
          echo "WARNING: $ERRORS resources still present. Manual cleanup may be needed."
          exit 1
        fi

        echo "Deprovision verified: all resources cleaned up"
```

### tekton/pipelines/deprovision.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: deprovision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string

  tasks:
    - name: delete-cluster-resources
      taskRef:
        name: delete-cluster-resources
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: wait-hive-uninstall
      taskRef:
        name: wait-hive-uninstall
      runAfter:
        - delete-cluster-resources
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      timeout: "30m"

    - name: cleanup-hub-artifacts
      taskRef:
        name: cleanup-hub-artifacts
      runAfter:
        - wait-hive-uninstall
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: verify-deprovision
      taskRef:
        name: verify-deprovision
      runAfter:
        - cleanup-hub-artifacts
      params:
        - name: cluster-name
          value: $(params.cluster-name)
```

Update `tekton/pipelines/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - provision.yaml
  - deprovision.yaml
```

Update `tekton/tasks/kustomization.yaml` to add the new tasks:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - create-cluster-namespace.yaml
  - apply-crossplane-credentials.yaml
  - wait-for-aws-credentials.yaml
  - validate-cluster-inputs.yaml
  - apply-cluster-crs.yaml
  - wait-for-hive-ready.yaml
  - wait-for-managed-cluster.yaml
  - extract-spoke-kubeconfig.yaml
  - label-for-post-provision.yaml
  - delete-cluster-resources.yaml
  - wait-hive-uninstall.yaml
  - cleanup-hub-artifacts.yaml
  - verify-deprovision.yaml
```

### Acceptance criteria

- [ ] Deprovision pipeline runs successfully on test-cluster-01
- [ ] AWS resources fully cleaned up (no orphaned EC2, LBs, etc.)
- [ ] Namespace, ManagedCluster, ClusterDeployment all gone from hub
- [ ] No custom finalizers used anywhere
- [ ] Total deprovision time < 25 min, deterministic (no 5-min poll tail)
- [ ] Re-provision test-cluster-01 via provision pipeline succeeds (full lifecycle proven)

### Rollback

If deprovision pipeline fails mid-run, resources are in known state (pipeline logs show exactly where it stopped). Resume manually from the failed task or re-run pipeline.

---

## Phase 4: Post-Provision (SSL + IDP + Tier Configuration)

> **Open question:** The post-provision approach is not yet decided. Two models are under consideration:
>
> 1. **Tekton pipeline** (original design, shown below) — imperative tasks for SSL cert derivation, IDP secret push, tier-specific operator installation. Full pipeline controls ordering.
> 2. **Layered ArgoCD ApplicationSets** — tier-specific workloads (operators, config) delivered declaratively via multiple ApplicationSets with different ACM Placement label selectors (see Phase 5). This would handle tier branching without a Tekton pipeline.
>
> **What is clear:**
> - SSL cert derivation (request on hub, derive leaf cert, push to spoke across trust boundary) requires imperative steps — cannot be pure ArgoCD.
> - IDP secret push to spoke also requires imperative steps.
> - Tier-specific operator delivery (virt operators, AI operators) *can* be handled by layered ApplicationSets.
> - The layered ApplicationSet pattern from Phase 5 may absorb the tier-branching responsibilities originally planned for this phase.
>
> **Decision needed before implementation.** The Tekton task definitions below are preserved as reference for the imperative steps. The tier-branching tasks (`apply-tier-virt`, `apply-tier-ai`, `apply-tier-base`, `verify-tier`) may be replaced by ApplicationSets.

**Goal**: Handle post-provision configuration: SSL/TLS setup, IDP configuration, and tier-specific workload delivery. The imperative steps (SSL, IDP) will use Tekton; the tier workload delivery approach is TBD.

### Files to create

```
fleet/tekton/
├── tasks/
│   ├── setup-letsencrypt-issuer.yaml
│   ├── request-spoke-certificate.yaml
│   ├── wait-cert-ready.yaml
│   ├── push-tls-to-spoke.yaml
│   ├── patch-spoke-ingress.yaml
│   ├── apply-baseline.yaml
│   ├── apply-tier-virt.yaml
│   ├── apply-tier-ai.yaml
│   ├── apply-tier-base.yaml
│   ├── verify-tier.yaml
│   ├── apply-idp-to-spoke.yaml
│   ├── verify-idp.yaml
│   ├── mark-bootstrapped.yaml
│   └── trigger-post-provision.yaml
└── pipelines/
    └── post-provision.yaml

fleet/workloads/
├── base/
│   ├── kustomization.yaml
│   ├── rbac.yaml
│   └── network-policies.yaml
├── virt/
│   ├── kustomization.yaml
│   ├── cnv-subscription.yaml
│   └── hyperconverged.yaml
└── ai/
    ├── kustomization.yaml
    ├── nfd-subscription.yaml
    ├── nvidia-gpu-operator.yaml
    ├── openshift-ai-subscription.yaml
    └── datasciencecluster.yaml
```

### tekton/tasks/setup-letsencrypt-issuer.yaml

Creates a per-cluster ClusterIssuer using the cluster's own AWS credentials for Route53 DNS-01 validation. Mirrors labargocd's `ssl-setup-job.yaml` behavior.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: setup-letsencrypt-issuer
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: base-domain
      type: string
      default: openshiftpartnerlabs.com
    - name: acme-email
      type: string
      default: partner-lab@redhat.com
    - name: region
      type: string
      default: us-east-1
  steps:
    - name: create-issuer
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        DOMAIN="$(params.base-domain)"
        EMAIL="$(params.acme-email)"
        REGION="$(params.region)"

        ACCESS_KEY=$(oc get secret aws-credentials -n "$CLUSTER" \
          -o jsonpath='{.data.aws_access_key_id}' | base64 -d)
        SECRET_KEY=$(oc get secret aws-credentials -n "$CLUSTER" \
          -o jsonpath='{.data.aws_secret_access_key}' | base64 -d)

        oc create secret generic cert-manager-aws-credentials \
          -n cert-manager \
          --from-literal=access-key-id="$ACCESS_KEY" \
          --from-literal=secret-access-key="$SECRET_KEY" \
          --dry-run=client -o yaml | oc apply -f -

        cat <<EOF | oc apply -f -
        apiVersion: cert-manager.io/v1
        kind: ClusterIssuer
        metadata:
          name: letsencrypt-${CLUSTER}
        spec:
          acme:
            server: https://acme-v02.api.letsencrypt.org/directory
            email: ${EMAIL}
            privateKeySecretRef:
              name: letsencrypt-${CLUSTER}-account-key
            solvers:
              - dns01:
                  route53:
                    region: ${REGION}
                    accessKeyIDSecretRef:
                      name: cert-manager-aws-credentials
                      namespace: cert-manager
                      key: access-key-id
                    secretAccessKeySecretRef:
                      name: cert-manager-aws-credentials
                      namespace: cert-manager
                      key: secret-access-key
                selector:
                  dnsZones:
                    - "${DOMAIN}"
        EOF

        echo "ClusterIssuer letsencrypt-${CLUSTER} created"
```

### tekton/tasks/request-spoke-certificate.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: request-spoke-certificate
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: base-domain
      type: string
      default: openshiftpartnerlabs.com
  steps:
    - name: request-cert
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        DOMAIN="$(params.base-domain)"

        cat <<EOF | oc apply -f -
        apiVersion: cert-manager.io/v1
        kind: Certificate
        metadata:
          name: ${CLUSTER}-wildcard-cert
          namespace: ${CLUSTER}
        spec:
          secretName: ${CLUSTER}-wildcard-tls
          issuerRef:
            name: letsencrypt-${CLUSTER}
            kind: ClusterIssuer
          dnsNames:
            - "*.apps.${CLUSTER}.${DOMAIN}"
            - "api.${CLUSTER}.${DOMAIN}"
          duration: 2160h
          renewBefore: 360h
        EOF

        echo "Certificate ${CLUSTER}-wildcard-cert requested"
```

### tekton/tasks/wait-cert-ready.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: wait-cert-ready
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: timeout
      type: string
      default: "10m"
  steps:
    - name: wait
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Waiting for certificate ${CLUSTER}-wildcard-cert to be ready..."
        oc wait --for=condition=Ready \
          certificate/"${CLUSTER}-wildcard-cert" \
          -n "$CLUSTER" \
          --timeout="$(params.timeout)"

        echo "Certificate ready"
```

### tekton/tasks/push-tls-to-spoke.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: push-tls-to-spoke
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  workspaces:
    - name: shared
  steps:
    - name: push
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        TLS_CRT=$(oc get secret "${CLUSTER}-wildcard-tls" -n "$CLUSTER" \
          -o jsonpath='{.data.tls\.crt}')
        TLS_KEY=$(oc get secret "${CLUSTER}-wildcard-tls" -n "$CLUSTER" \
          -o jsonpath='{.data.tls\.key}')

        export KUBECONFIG=/workspace/shared/kubeconfig

        echo "Waiting for spoke API to be reachable..."
        ELAPSED=0
        until oc --request-timeout=10s get ns openshift-ingress 2>/dev/null; do
          if [ "$ELAPSED" -ge 600 ]; then
            echo "ERROR: Spoke API not reachable after 10 minutes"
            exit 1
          fi
          sleep 10
          ELAPSED=$((ELAPSED + 10))
        done

        cat <<EOF | oc apply -f -
        apiVersion: v1
        kind: Secret
        metadata:
          name: ${CLUSTER}-wildcard-certificate
          namespace: openshift-ingress
        data:
          tls.crt: ${TLS_CRT}
          tls.key: ${TLS_KEY}
        type: kubernetes.io/tls
        EOF

        echo "TLS certificate pushed to spoke openshift-ingress"
```

### tekton/tasks/patch-spoke-ingress.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: patch-spoke-ingress
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  workspaces:
    - name: shared
  steps:
    - name: patch
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        export KUBECONFIG=/workspace/shared/kubeconfig

        oc patch ingresscontroller default \
          -n openshift-ingress-operator \
          --type=merge \
          -p "{\"spec\":{\"defaultCertificate\":{\"name\":\"${CLUSTER}-wildcard-certificate\"}}}"

        echo "Spoke IngressController patched with custom TLS certificate"
```

### tekton/tasks/apply-baseline.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-baseline
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: git-repo-url
      type: string
      default: https://github.com/redhat-openshift-partner-labs/fleet.git
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: shared
  steps:
    - name: apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        export KUBECONFIG=/workspace/shared/kubeconfig

        cd /workspace/shared
        if [ ! -d repo ]; then
          git clone --depth 1 "$(params.git-repo-url)" repo
        fi

        echo "Applying baseline workloads..."
        kustomize build repo/workloads/base | oc apply -f -

        echo "Baseline workloads applied to spoke"
```

### tekton/tasks/apply-tier-virt.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-tier-virt
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: git-repo-url
      type: string
      default: https://github.com/redhat-openshift-partner-labs/fleet.git
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: shared
  steps:
    - name: apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        export KUBECONFIG=/workspace/shared/kubeconfig

        cd /workspace/shared
        if [ ! -d repo ]; then
          git clone --depth 1 "$(params.git-repo-url)" repo
        fi

        echo "Applying virt tier workloads..."
        kustomize build repo/workloads/virt | oc apply -f -

        echo "Waiting for OpenShift Virtualization operator..."
        oc wait --for=condition=Available \
          csv -l operators.coreos.com/kubevirt-hyperconverged.openshift-cnv \
          -n openshift-cnv \
          --timeout=10m 2>/dev/null || echo "CSV wait skipped (may need manual check)"

        echo "Virt tier applied"
```

### tekton/tasks/apply-tier-ai.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-tier-ai
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: git-repo-url
      type: string
      default: https://github.com/redhat-openshift-partner-labs/fleet.git
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: shared
  steps:
    - name: apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        export KUBECONFIG=/workspace/shared/kubeconfig

        cd /workspace/shared
        if [ ! -d repo ]; then
          git clone --depth 1 "$(params.git-repo-url)" repo
        fi

        echo "Applying AI tier workloads..."
        kustomize build repo/workloads/ai | oc apply -f -

        echo "AI tier applied"
```

### tekton/tasks/apply-tier-base.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-tier-base
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  workspaces:
    - name: shared
  steps:
    - name: noop
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        echo "Base tier: no additional operators to install beyond baseline"
```

### tekton/tasks/verify-tier.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: verify-tier
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: tier
      type: string
  workspaces:
    - name: shared
  steps:
    - name: verify
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        export KUBECONFIG=/workspace/shared/kubeconfig
        TIER="$(params.tier)"

        echo "Verifying tier: $TIER..."

        case "$TIER" in
          virt)
            echo "Checking HyperConverged status..."
            oc wait --for=condition=Available \
              hyperconverged/kubevirt-hyperconverged \
              -n openshift-cnv \
              --timeout=15m 2>/dev/null || echo "HyperConverged check: manual verification needed"
            ;;
          ai)
            echo "Checking DataScienceCluster status..."
            oc wait --for=condition=Ready \
              datasciencecluster \
              --all \
              -n redhat-ods-operator \
              --timeout=15m 2>/dev/null || echo "DSC check: manual verification needed"
            ;;
          base)
            echo "Checking baseline operator health..."
            oc get clusteroperators --no-headers | while read line; do
              NAME=$(echo "$line" | awk '{print $1}')
              AVAIL=$(echo "$line" | awk '{print $3}')
              if [ "$AVAIL" != "True" ]; then
                echo "  WARNING: ClusterOperator $NAME not Available"
              fi
            done
            ;;
        esac

        echo "Tier $TIER verification complete"
```

### tekton/tasks/apply-idp-to-spoke.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: apply-idp-to-spoke
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: idp-secret-name
      type: string
      default: idp-client-config
    - name: idp-secret-namespace
      type: string
      default: openshift-gitops
  workspaces:
    - name: shared
  steps:
    - name: apply
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        echo "Reading IDP config from hub..."
        CLIENT_ID=$(oc get secret "$(params.idp-secret-name)" \
          -n "$(params.idp-secret-namespace)" \
          -o jsonpath='{.data.client-id}' | base64 -d)
        CLIENT_SECRET=$(oc get secret "$(params.idp-secret-name)" \
          -n "$(params.idp-secret-namespace)" \
          -o jsonpath='{.data.client-secret}' | base64 -d)
        ISSUER_URL=$(oc get secret "$(params.idp-secret-name)" \
          -n "$(params.idp-secret-namespace)" \
          -o jsonpath='{.data.issuer-url}' | base64 -d)

        export KUBECONFIG=/workspace/shared/kubeconfig

        oc create secret generic oidc-client-secret \
          -n openshift-config \
          --from-literal=clientSecret="$CLIENT_SECRET" \
          --dry-run=client -o yaml | oc apply -f -

        cat <<EOF | oc apply -f -
        apiVersion: config.openshift.io/v1
        kind: OAuth
        metadata:
          name: cluster
        spec:
          identityProviders:
            - name: oidc
              challenge: false
              login: true
              mappingMethod: claim
              type: OpenID
              openID:
                clientID: ${CLIENT_ID}
                clientSecret:
                  name: oidc-client-secret
                issuer: ${ISSUER_URL}
                claims:
                  preferredUsername:
                    - preferred_username
                  name:
                    - name
                  email:
                    - email
        EOF

        echo "IDP configured on spoke"
```

### tekton/tasks/verify-idp.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: verify-idp
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: base-domain
      type: string
      default: openshiftpartnerlabs.com
  workspaces:
    - name: shared
  steps:
    - name: verify
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        DOMAIN="$(params.base-domain)"
        OAUTH_URL="https://oauth-openshift.apps.${CLUSTER}.${DOMAIN}/.well-known/oauth-authorization-server"

        echo "Verifying IDP on spoke..."

        ELAPSED=0
        until curl -sk "$OAUTH_URL" | grep -q issuer 2>/dev/null; do
          if [ "$ELAPSED" -ge 300 ]; then
            echo "WARNING: OAuth endpoint not responding after 5 minutes. IDP may need manual verification."
            exit 0
          fi
          sleep 15
          ELAPSED=$((ELAPSED + 15))
        done

        echo "IDP verified: OAuth endpoint responding"
```

### tekton/tasks/mark-bootstrapped.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: mark-bootstrapped
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
  steps:
    - name: label
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"

        oc label managedcluster/"$CLUSTER" \
          bootstrapped=true \
          --overwrite

        echo "ManagedCluster $CLUSTER labeled bootstrapped=true"
        echo "ArgoCD ApplicationSet will now pick up this cluster for day-2 workloads"
```

### tekton/tasks/trigger-post-provision.yaml

Added to the end of the provision pipeline to chain into post-provision.

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: trigger-post-provision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: tier
      type: string
      default: base
    - name: git-repo-url
      type: string
    - name: git-revision
      type: string
      default: main
    - name: base-domain
      type: string
      default: openshiftpartnerlabs.com
    - name: region
      type: string
      default: us-east-1
  steps:
    - name: trigger
      image: registry.redhat.io/openshift4/ose-cli:v4.14
      script: |
        #!/usr/bin/env bash
        set -euo pipefail
        CLUSTER="$(params.cluster-name)"
        TIER="$(params.tier)"

        cat <<EOF | oc create -f -
        apiVersion: tekton.dev/v1
        kind: PipelineRun
        metadata:
          generateName: post-provision-${CLUSTER}-
          namespace: openshift-pipelines
        spec:
          pipelineRef:
            name: post-provision
          params:
            - name: cluster-name
              value: ${CLUSTER}
            - name: tier
              value: ${TIER}
            - name: base-domain
              value: $(params.base-domain)
            - name: region
              value: $(params.region)
            - name: git-repo-url
              value: $(params.git-repo-url)
            - name: git-revision
              value: $(params.git-revision)
          workspaces:
            - name: shared-workspace
              emptyDir: {}
          serviceAccountName: fleet-pipeline
        EOF

        echo "Post-provision pipeline triggered for $CLUSTER (tier: $TIER)"
```

### tekton/pipelines/post-provision.yaml

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: post-provision
  namespace: openshift-pipelines
spec:
  params:
    - name: cluster-name
      type: string
    - name: tier
      type: string
      default: base
    - name: base-domain
      type: string
      default: openshiftpartnerlabs.com
    - name: region
      type: string
      default: us-east-1
    - name: git-repo-url
      type: string
      default: https://github.com/redhat-openshift-partner-labs/fleet.git
    - name: git-revision
      type: string
      default: main
  workspaces:
    - name: shared-workspace

  tasks:
    - name: extract-spoke-kubeconfig
      taskRef:
        name: extract-spoke-kubeconfig
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: setup-letsencrypt-issuer
      taskRef:
        name: setup-letsencrypt-issuer
      runAfter:
        - extract-spoke-kubeconfig
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: base-domain
          value: $(params.base-domain)
        - name: region
          value: $(params.region)

    - name: request-spoke-certificate
      taskRef:
        name: request-spoke-certificate
      runAfter:
        - setup-letsencrypt-issuer
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: base-domain
          value: $(params.base-domain)

    - name: wait-cert-ready
      taskRef:
        name: wait-cert-ready
      runAfter:
        - request-spoke-certificate
      params:
        - name: cluster-name
          value: $(params.cluster-name)

    - name: push-tls-to-spoke
      taskRef:
        name: push-tls-to-spoke
      runAfter:
        - wait-cert-ready
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: patch-spoke-ingress
      taskRef:
        name: patch-spoke-ingress
      runAfter:
        - push-tls-to-spoke
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: apply-baseline
      taskRef:
        name: apply-baseline
      runAfter:
        - patch-spoke-ingress
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
      workspaces:
        - name: shared
          workspace: shared-workspace

    # Tier branching: virt
    - name: apply-tier-virt
      when:
        - input: $(params.tier)
          operator: in
          values: ["virt"]
      taskRef:
        name: apply-tier-virt
      runAfter:
        - apply-baseline
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
      workspaces:
        - name: shared
          workspace: shared-workspace

    # Tier branching: ai
    - name: apply-tier-ai
      when:
        - input: $(params.tier)
          operator: in
          values: ["ai"]
      taskRef:
        name: apply-tier-ai
      runAfter:
        - apply-baseline
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
      workspaces:
        - name: shared
          workspace: shared-workspace

    # Tier branching: base (noop)
    - name: apply-tier-base
      when:
        - input: $(params.tier)
          operator: in
          values: ["base"]
      taskRef:
        name: apply-tier-base
      runAfter:
        - apply-baseline
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: verify-tier
      taskRef:
        name: verify-tier
      runAfter:
        - apply-tier-virt
        - apply-tier-ai
        - apply-tier-base
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: tier
          value: $(params.tier)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: apply-idp-to-spoke
      taskRef:
        name: apply-idp-to-spoke
      runAfter:
        - verify-tier
      params:
        - name: cluster-name
          value: $(params.cluster-name)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: verify-idp
      taskRef:
        name: verify-idp
      runAfter:
        - apply-idp-to-spoke
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: base-domain
          value: $(params.base-domain)
      workspaces:
        - name: shared
          workspace: shared-workspace

    - name: mark-bootstrapped
      taskRef:
        name: mark-bootstrapped
      runAfter:
        - verify-idp
      params:
        - name: cluster-name
          value: $(params.cluster-name)
```

### Update provision pipeline

Add `trigger-post-provision` as final task in `tekton/pipelines/provision.yaml`:

```yaml
    # Add after label-for-post-provision task:
    - name: trigger-post-provision
      taskRef:
        name: trigger-post-provision
      runAfter:
        - label-for-post-provision
      params:
        - name: cluster-name
          value: $(params.cluster-name)
        - name: tier
          value: $(params.tier)
        - name: region
          value: $(params.region)
        - name: git-repo-url
          value: $(params.git-repo-url)
        - name: git-revision
          value: $(params.git-revision)
```

### Acceptance criteria

- [ ] Post-provision pipeline runs end-to-end on test cluster
- [ ] Let's Encrypt wildcard cert issued and pushed to spoke
- [ ] Spoke IngressController using custom TLS cert
- [ ] Tier branching works: base/virt/ai paths execute correctly based on param
- [ ] IDP configured on spoke, OAuth endpoint responding
- [ ] Cluster labeled `bootstrapped=true`
- [ ] Provision pipeline chains into post-provision automatically

### Rollback

Post-provision is additive. If it fails, spoke cluster is provisioned but unconfigured. Re-run post-provision pipeline from the failed task.

---

## Phase 5: ApplicationSet Day-2 Delivery

**Goal**: Replace per-cluster ArgoCD Applications with ApplicationSet using ACM cluster generator. Clusters labeled `bootstrapped=true` automatically receive day-2 workloads.

### Files to create

```
fleet/
├── bootstrap/
│   └── argocd-applicationset.yaml
└── workloads/
    ├── base/
    │   ├── kustomization.yaml
    │   ├── rbac.yaml
    │   └── network-policies.yaml
    ├── virt/
    │   ├── kustomization.yaml
    │   ├── cnv-subscription.yaml
    │   └── hyperconverged.yaml
    └── ai/
        ├── kustomization.yaml
        ├── nfd-subscription.yaml
        ├── nvidia-gpu-operator.yaml
        ├── openshift-ai-subscription.yaml
        └── datasciencecluster.yaml
```

### bootstrap/argocd-applicationset.yaml

One ApplicationSet per tier. Clusters with `bootstrapped=true` and matching `tier` label get the corresponding workloads.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: fleet-workloads-base
  namespace: openshift-gitops
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: fleet-workloads
        requeueAfterSeconds: 180
  template:
    metadata:
      name: workload-base-{{name}}
    spec:
      project: default
      source:
        repoURL: https://github.com/redhat-openshift-partner-labs/fleet.git
        targetRevision: main
        path: workloads/base
      destination:
        server: "{{server}}"
        namespace: fleet-workloads
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
---
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: fleet-workloads-virt
  namespace: openshift-gitops
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: fleet-workloads-virt
        requeueAfterSeconds: 180
  template:
    metadata:
      name: workload-virt-{{name}}
    spec:
      project: default
      source:
        repoURL: https://github.com/redhat-openshift-partner-labs/fleet.git
        targetRevision: main
        path: workloads/virt
      destination:
        server: "{{server}}"
        namespace: openshift-cnv
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
---
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: fleet-workloads-ai
  namespace: openshift-gitops
spec:
  generators:
    - clusterDecisionResource:
        configMapRef: acm-placement
        labelSelector:
          matchLabels:
            cluster.open-cluster-management.io/placement: fleet-workloads-ai
        requeueAfterSeconds: 180
  template:
    metadata:
      name: workload-ai-{{name}}
    spec:
      project: default
      source:
        repoURL: https://github.com/redhat-openshift-partner-labs/fleet.git
        targetRevision: main
        path: workloads/ai
      destination:
        server: "{{server}}"
        namespace: redhat-ods-operator
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
---
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: fleet-workloads
  namespace: openshift-gitops
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            bootstrapped: "true"
---
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: fleet-workloads-virt
  namespace: openshift-gitops
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            bootstrapped: "true"
            tier: virt
---
apiVersion: cluster.open-cluster-management.io/v1beta1
kind: Placement
metadata:
  name: fleet-workloads-ai
  namespace: openshift-gitops
spec:
  predicates:
    - requiredClusterSelector:
        labelSelector:
          matchLabels:
            bootstrapped: "true"
            tier: ai
```

### Acceptance criteria

- [ ] ApplicationSets deployed to hub
- [ ] Placements created and evaluating
- [ ] Test cluster with `bootstrapped=true` + `tier=base` gets base workloads via ApplicationSet
- [ ] ArgoCD UI shows auto-generated Applications
- [ ] No per-cluster Application YAML needed

---

## Verification

### Per-phase testing

| Phase | Test |
|-------|------|
| 1 | `oc get csv -n openshift-operators` shows Tekton + cert-manager installed |
| 2 | `tkn pipeline start provision -p cluster-name=test-cluster-01 -w name=shared-workspace,emptyDir="" -n openshift-pipelines` completes |
| 3 | `tkn pipeline start deprovision -p cluster-name=test-cluster-01 -n openshift-pipelines` completes, all resources gone |
| 4 | `tkn pipeline start post-provision -p cluster-name=test-cluster-01 -p tier=base -w name=shared-workspace,emptyDir="" -n openshift-pipelines` completes, cert + IDP configured |
| 5 | `oc get applicationset -n openshift-gitops` shows fleet-workloads-*, test cluster gets auto-generated Application |
| 6 | Each migrated cluster: `oc get managedcluster <name>` shows healthy, workloads stable |
| 7 | `oc get cronjob -n openshift-gitops` shows no deprovision-cleanup, `oc get secrets -A -l openshiftpartnerlabs.com/deprovision-pending=true` returns empty |

### End-to-end lifecycle test

After all phases:
1. Create `clusters/e2e-test/` in fleet repo, push to main
2. Webhook fires -> provision pipeline -> post-provision pipeline -> cluster bootstrapped
3. ApplicationSet delivers day-2 workloads
4. Delete `clusters/e2e-test/`, trigger deprovision pipeline
5. All resources cleaned up, no orphans
