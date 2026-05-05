# Hub Cluster Setup Guide

This directory contains the complete declarative configuration for setting up an OpenShift hub cluster for fleet management using the Red Hat OpenShift Partner Labs architecture.

## Overview

The hub cluster serves as the central control plane for managing a fleet of OpenShift clusters. It provides:

- **Cluster Lifecycle Management** via Advanced Cluster Management (ACM)
- **Infrastructure Provisioning** via Crossplane
- **GitOps Delivery** via ArgoCD (OpenShift GitOps)
- **Workflow Orchestration** via Tekton (OpenShift Pipelines)
- **Certificate Management** via cert-manager

## Quick Start

### Automated Installation (Recommended)

**Using Make (from project root):**
```bash
make hub-install
```

**Direct script execution:**
```bash
cd hub-config/
./install-hub-config.sh
```

### Manual Installation
```bash
# 1. Generate dynamic channel configuration
./generate-channels.sh

# 2. Deploy all hub cluster operators  
oc apply -k .

# 3. Wait for operators to install, then re-apply for CRs
oc apply -k .

# 4. Verify installation
oc get csv -A | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)"
oc get providers  # Check crossplane providers
oc get multiclusterhub -n open-cluster-management
```

## Prerequisites

### Cluster Requirements
- OpenShift 4.12+ cluster with cluster-admin privileges
- Minimum 16 vCPU, 64GB RAM, 200GB storage
- Internet connectivity for pulling operator images and helm charts
- Red Hat operator catalog available (`redhat-operators` source)

### Credentials Setup
Before applying the configuration, ensure you have:

1. **AWS Credentials** (for Crossplane):
   ```bash
   oc create secret generic aws-credentials \
     --from-literal=credentials="$(cat ~/.aws/credentials)" \
     -n crossplane-system
   ```

2. **Container Registry Access** (if using private registries):
   ```bash
   oc create secret docker-registry quay-pull-secret \
     --docker-server=quay.io/rhopl \
     --docker-username=<username> \
     --docker-password=<token> \
     -n <target-namespace>
   ```

## Installation Steps

### Step 1: Clone and Navigate
```bash
git clone <fleet-repo-url>
cd fleet/hub-config
```

### Step 2: Generate Dynamic Channel Configuration
```bash
# Connect to your OpenShift cluster first
oc login <cluster-url>

# Generate latest operator channels
./generate-channels.sh
```

This script queries your cluster's package manifests and automatically selects the latest appropriate channels for each operator, ensuring you get the most up-to-date versions available.

### Step 3: Review Configuration
```bash
# Check the complete configuration with updated channels
oc apply -k . --dry-run=client -o yaml | less

# Verify subscription files have been updated
grep -r "channel:" */subscription.yaml
```

### Step 4: Deploy Operators
```bash
# Apply the complete hub configuration
oc apply -k .

# Monitor operator installation progress
watch oc get csv -A
```

### Step 4: Verify Installation
See [Verification](#verification) section below.

## Uninstallation

### Automated Uninstallation (Recommended)

**Using Make (from project root):**
```bash
make hub-uninstall
```

**Direct script execution:**
```bash
cd hub-config/
./uninstall-hub-config.sh
```

This script removes all components in the proper order to avoid stuck resources:
1. **Custom Resources**: MultiClusterHub, Providers, ProviderConfigs
2. **Infrastructure**: Crossplane installation job
3. **Operators**: Subscriptions and ClusterServiceVersions  
4. **RBAC**: ClusterRoles and ClusterRoleBindings
5. **Namespaces**: Clean removal after resources are gone

### Manual Uninstallation
```bash
# Remove custom resources first
oc delete multiclusterhub --all --all-namespaces
oc delete providers --all
oc delete providerconfig.aws.upbound.io --all

# Remove operators
oc delete subscriptions -n openshift-operators cert-manager openshift-gitops-operator openshift-pipelines-operator
oc delete subscriptions -n open-cluster-management advanced-cluster-management
oc delete csv --all --all-namespaces

# Remove namespaces
oc delete namespace cert-manager crossplane-system openshift-gitops openshift-pipelines multicluster-engine open-cluster-management
```

**⚠️ Important**: Always remove custom resources before operators to avoid stuck namespaces.

## Dynamic Channel Management

This hub-config uses a dynamic channel management system to ensure you always get the latest available operator versions without hardcoding specific channels in your manifests.

### How It Works

1. **Placeholder Channels**: Subscription files use placeholders (e.g., `CERT_MANAGER_CHANNEL`) instead of hardcoded channels
2. **Query Script**: The `generate-channels.sh` script queries your cluster's package manifests  
3. **Smart Selection**: For each operator, it finds and selects the most appropriate channel:
   - **cert-manager**: Latest `stable-v*` channel
   - **ACM**: Latest `release-*` channel  
   - **GitOps**: Latest `gitops-*` channel
   - **Pipelines**: Latest versioned channel (avoids generic "latest")
4. **File Updates**: The script directly updates subscription files with discovered channels

### Usage

```bash
# Generate channels for current cluster
./generate-channels.sh

# Output example:
# 🔒 cert-manager: stable-v1.19
# 🌐 ACM: release-2.16  
# 📦 GitOps: gitops-1.20
# 🔄 Pipelines: pipelines-1.22
```

### Benefits

- ✅ **Always Current**: Automatically uses latest available versions
- ✅ **Cluster Aware**: Adapts to what's actually available in your cluster's catalogs
- ✅ **Version Specific**: Avoids generic "latest" channels for better reproducibility
- ✅ **No Hardcoding**: Eliminates outdated channel references in git

### Channel Update Workflow

```bash
# Update channels to latest available
./generate-channels.sh

# Review changes
git diff

# Commit updated channels
git add . && git commit -m "chore: update operator channels to latest available"

# Deploy with new channels
oc apply -k .
```

## Architecture

### Directory Structure
```
hub-config/
├── README.md                    # This guide
├── kustomization.yaml          # Root orchestrator
├── namespaces.yaml             # All required namespaces
├── generate-channels.sh        # Dynamic channel discovery
├── install-hub-config.sh       # Automated installation
├── uninstall-hub-config.sh     # Graceful removal
├── cert-manager/               # SSL/TLS certificate automation
│   ├── kustomization.yaml
│   └── subscription.yaml
├── tekton/                     # Pipeline workflows
│   ├── kustomization.yaml
│   └── subscription.yaml
├── argocd/                     # GitOps delivery
│   ├── kustomization.yaml
│   └── subscription.yaml
├── acm/                        # Cluster lifecycle management
│   ├── kustomization.yaml
│   ├── subscription.yaml       # Namespace-scoped installation
│   └── multiclusterhub.yaml    # ACM hub instance
└── crossplane/                 # Infrastructure as code
    ├── kustomization.yaml
    ├── installation/           # Helm-based installation
    │   ├── kustomization.yaml
    │   ├── helm-job.yaml       # Declarative helm job
    │   └── rbac.yaml           # Installation permissions
    ├── rbac/                   # OpenShift security
    │   ├── kustomization.yaml
    │   └── scc-binding.yaml    # SCC bindings for providers
    ├── provider.yaml           # AWS IAM provider
    └── providerconfig.yaml     # AWS credentials reference
```

### Component Details

#### 🔒 **cert-manager** (Certificate Management)
- **Operator**: `openshift-cert-manager-operator` (Red Hat)
- **Namespace**: Cluster-wide (`AllNamespaces`)
- **Purpose**: Automates SSL/TLS certificate lifecycle
- **Channel**: `stable-v1`

#### 🔄 **Tekton/OpenShift Pipelines** (Workflow Engine)
- **Operator**: `openshift-pipelines-operator-rh` (Red Hat)
- **Namespace**: `openshift-pipelines`
- **Purpose**: Executes cluster provisioning and lifecycle workflows
- **Channel**: `latest`

#### 📦 **ArgoCD/OpenShift GitOps** (GitOps Delivery)
- **Operator**: `openshift-gitops-operator` (Red Hat)
- **Namespace**: `openshift-gitops`
- **Purpose**: Delivers hub configuration and spoke workloads
- **Channel**: `gitops-1.13`

#### 🌐 **Advanced Cluster Management** (Cluster Fleet Management)
- **Operator**: `advanced-cluster-management` (Red Hat)
- **Namespace**: `open-cluster-management` (namespace-scoped)
- **Purpose**: Manages cluster lifecycle, policies, and fleet membership
- **Channel**: `release-2.16`
- **Custom Resource**: `MultiClusterHub` for hub functionality

#### ☁️ **Crossplane** (Infrastructure Provisioning)
- **Installation**: Helm chart v2.2.0 (via declarative Kubernetes Job)
- **Namespace**: `crossplane-system`
- **Provider**: AWS IAM v1.7.0 for user/credential management
- **Purpose**: Provisions infrastructure resources (IAM users, policies, etc.)

## Verification

### 1. Operator Status
```bash
# All operators should show "Succeeded"
oc get csv -A | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)"

# Expected output:
# cert-manager-operator.v1.19.0                      Succeeded
# openshift-gitops-operator.v1.13.3                  Succeeded  
# openshift-pipelines-operator-rh.v1.22.0            Succeeded
# advanced-cluster-management.v2.16.0                Succeeded
```

### 2. Crossplane Status
```bash
# Check crossplane installation
oc get jobs -n crossplane-system
oc get pods -n crossplane-system

# Check providers
oc get providers
# Should show: provider-aws-iam (True, True)

# Check provider configuration
oc get providerconfig.aws.upbound.io
# Should show: default
```

### 3. ACM Hub Status
```bash
# Check MultiClusterHub
oc get multiclusterhub -n open-cluster-management
# Status should progress: Installing → Running

# Check ACM components
oc get pods -n open-cluster-management
```

### 4. ArgoCD Status
```bash
# Check ArgoCD instance
oc get argocds -n openshift-gitops
# Should show: openshift-gitops (Available)

# Check ArgoCD UI accessibility
oc get route openshift-gitops-server -n openshift-gitops
```

### 5. Web Console Integration
- **Pipelines**: Check that "Pipelines" tab appears in OpenShift console
- **ACM**: Access ACM dashboard via console
- **ArgoCD**: Access GitOps interface

## Troubleshooting

### Common Issues

#### Operator Installation Failures
```bash
# Check subscription status
oc get subscriptions -A
oc get installplans -A

# Check events for errors
oc get events -A --sort-by='.lastTimestamp' | tail -20
```

#### Crossplane Installation Issues
```bash
# Check helm job logs
oc logs job/crossplane-helm-installer -n crossplane-system

# Common fixes:
# - Network connectivity issues (helm repo access)
# - Missing openssl package (already included in config)
# - Insufficient RBAC (ServiceAccount has cluster-admin)
```

#### ACM Installation Issues
```bash
# ACM requires namespace-scoped installation
# Check OperatorGroup configuration
oc describe operatorgroup -n open-cluster-management

# Verify no conflicting installations in openshift-operators
oc get csv -n openshift-operators | grep advanced-cluster-management
```

#### Provider Configuration Issues
```bash
# Ensure AWS credentials secret exists
oc get secret aws-credentials -n crossplane-system

# Check provider health
oc describe provider provider-aws-iam
```

### Recovery Procedures

#### Clean Restart
```bash
# Remove all components
oc delete -k hub-config/

# Clean up any remaining resources
oc delete namespace crossplane-system open-cluster-management

# Wait for cleanup, then reapply
oc apply -k hub-config/
```

#### ACM Only Reset
```bash
# Remove just ACM components
oc delete multiclusterhub multiclusterhub -n open-cluster-management
oc delete csv -n open-cluster-management -l operators.coreos.com/advanced-cluster-management.open-cluster-management

# Reapply ACM config
oc apply -k hub-config/acm/
```

## Support

### Documentation
- [OpenShift GitOps Documentation](https://docs.openshift.com/gitops/)
- [Advanced Cluster Management Documentation](https://access.redhat.com/documentation/en-us/red_hat_advanced_cluster_management_for_kubernetes/)
- [Crossplane Documentation](https://docs.crossplane.io/)
- [OpenShift Pipelines Documentation](https://docs.openshift.com/pipelines/)

### Troubleshooting Resources
- Check operator logs in respective namespaces
- Review Red Hat Knowledge Base for known issues
- OpenShift support cases for cluster-specific issues

---

## Quick Reference

### Key Commands

**Using Make targets (from project root):**
```bash
# Full hub cluster setup
make hub-install

# Check installation status
make hub-status

# Update operator channels
make hub-channels

# Graceful removal
make hub-uninstall

# Check prerequisites
make hub-check
```

**Using scripts directly:**
```bash
# Automated installation (recommended)
./install-hub-config.sh

# Manual deployment
./generate-channels.sh && oc apply -k .

# Check operator status
oc get csv -A | grep -v packageserver

# Check crossplane
oc get providers && oc get providerconfig.aws.upbound.io

# Check ACM
oc get multiclusterhub -A

# Check ArgoCD
oc get argocds -A

# Graceful uninstallation
./uninstall-hub-config.sh
```

### Available Scripts & Targets
- **`make hub-install`** / **`install-hub-config.sh`**: Automated installation with proper sequencing
- **`make hub-uninstall`** / **`uninstall-hub-config.sh`**: Graceful removal of all components
- **`make hub-channels`** / **`generate-channels.sh`**: Discovers and updates operator channels dynamically
- **`make hub-status`**: Check status of all hub cluster operators
- **`make hub-check`**: Verify prerequisites and cluster connectivity

### Important Namespaces
- `openshift-operators`: cert-manager, tekton, argocd operators
- `open-cluster-management`: ACM operator and hub
- `crossplane-system`: Crossplane core and providers
- `openshift-gitops`: ArgoCD instances
- `openshift-pipelines`: Tekton resources

This hub cluster configuration provides a complete foundation for OpenShift fleet management with all required operators and proper OpenShift integration.