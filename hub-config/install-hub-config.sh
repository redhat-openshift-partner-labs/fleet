#!/bin/bash

# Install hub-config with proper sequencing
# This script handles the two-phase installation automatically

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Hub Cluster Operator Installation"
echo "===================================="

# Check cluster connectivity
if ! oc cluster-info >/dev/null 2>&1; then
    echo "❌ Error: Not connected to an OpenShift cluster"
    echo "   Please login with 'oc login' first"
    exit 1
fi

echo "✅ Connected to cluster: $(oc config current-context)"
echo ""

# Step 1: Generate dynamic channels
echo "📡 Step 1: Generating dynamic operator channels..."
if [[ -f "${SCRIPT_DIR}/generate-channels.sh" ]]; then
    cd "${SCRIPT_DIR}"
    ./generate-channels.sh
else
    echo "❌ generate-channels.sh not found!"
    exit 1
fi

echo ""

# Step 2: Initial apply (operators, namespaces, RBAC - but NOT dependent resources)
echo "⚙️  Step 2: Installing operators and infrastructure..."
echo "   This will create namespaces, subscriptions, and RBAC..."

cd "${SCRIPT_DIR}"
echo "   📁 Applying namespaces..."
oc apply -f namespaces.yaml

echo "   📦 Applying operator subscriptions and groups..."
oc apply -f cert-manager/operatorgroup.yaml
oc apply -f cert-manager/subscription.yaml
oc apply -f tekton/subscription.yaml
oc apply -f argocd/subscription.yaml
oc apply -f acm/subscription.yaml
oc apply -f partner-labs-auth/operatorgroup.yaml
oc apply -f partner-labs-auth/subscription.yaml

echo "   ☁️  Applying Crossplane RBAC and installation job..."
oc apply -f crossplane/installation/rbac.yaml
oc apply -f crossplane/installation/helm-job.yaml
oc apply -f crossplane/rbac/scc-binding.yaml

echo ""

# Step 3: Wait for operator installations
echo "⏱️  Step 3: Waiting for operators to install..."
echo "   Monitoring ClusterServiceVersion status..."

expected_csvs=("cert-manager" "gitops" "pipelines" "advanced-cluster-management" "rhsso")
max_wait=600 # 10 minutes
wait_time=0
check_interval=15

while [[ $wait_time -lt $max_wait ]]; do
    echo "   Checking operator status... (${wait_time}s elapsed)"

    # Count succeeded CSVs
    succeeded_count=0
    total_found=0

    for csv_pattern in "${expected_csvs[@]}"; do
        csv_status=$(oc get csv -A --no-headers 2>/dev/null | grep "$csv_pattern" | head -1 | awk '{print $NF}' || echo "")
        if [[ -n "$csv_status" ]]; then
            total_found=$((total_found + 1))
            echo "     📦 ${csv_pattern}: ${csv_status}"
            if [[ "$csv_status" == "Succeeded" ]]; then
                succeeded_count=$((succeeded_count + 1))
            fi
        fi
    done

    # Check crossplane job status
    crossplane_job_status=$(oc get jobs -n crossplane-system crossplane-helm-installer -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || echo "False")
    echo "     ☁️  crossplane-job: $([ "$crossplane_job_status" == "True" ] && echo "Complete" || echo "Running")"

    # Check if all operators are ready
    if [[ $succeeded_count -eq ${#expected_csvs[@]} ]] && [[ "$crossplane_job_status" == "True" ]]; then
        echo ""
        echo "🎉 All operators installed successfully!"
        break
    fi

    # Check if any operators failed
    failed_csvs=$(oc get csv -A --no-headers 2>/dev/null | grep -E "(Failed|InstallCheckFailed)" | wc -l | tr -d ' \n' || echo "0")
    crossplane_job_failed=$(oc get jobs -n crossplane-system crossplane-helm-installer -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || echo "False")

    if [[ $failed_csvs -gt 0 ]] || [[ "$crossplane_job_failed" == "True" ]]; then
        echo ""
        echo "❌ Some operators failed to install:"
        oc get csv -A --no-headers 2>/dev/null | grep -E "(Failed|InstallCheckFailed)" || echo "   No failed CSVs found"
        if [[ "$crossplane_job_failed" == "True" ]]; then
            echo "   ❌ Crossplane helm job failed"
            echo "   Debug: oc logs job/crossplane-helm-installer -n crossplane-system"
        fi
        exit 1
    fi

    sleep $check_interval
    wait_time=$((wait_time + check_interval))
done

if [[ $wait_time -ge $max_wait ]]; then
    echo ""
    echo "⚠️  Timeout waiting for operators to install"
    echo "   Current status:"
    oc get csv -A --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)" || echo "   No operators found"
    echo "   You may need to check operator logs and retry manually"
    exit 1
fi

echo ""

# Step 4: Wait for CRDs and apply dependent resources
echo "🔧 Step 4: Waiting for operator CRDs and applying dependent resources..."

# Wait for ACM operator CRDs
echo "   ⏳ Waiting for ACM operator CRDs..."
acm_crd_wait=120
acm_elapsed=0
while [[ $acm_elapsed -lt $acm_crd_wait ]]; do
    if oc get crd multiclusterhubs.operator.open-cluster-management.io >/dev/null 2>&1; then
        echo "   ✅ ACM operator CRDs are ready"
        break
    fi
    echo "   ⏳ Waiting for ACM CRDs... (${acm_elapsed}s elapsed)"
    sleep 10
    acm_elapsed=$((acm_elapsed + 10))
done

if [[ $acm_elapsed -ge $acm_crd_wait ]]; then
    echo "   ⚠️  Timeout waiting for ACM CRDs, skipping MultiClusterHub..."
else
    echo "   📦 Applying MultiClusterHub..."
    cd "${SCRIPT_DIR}"
    oc apply -f acm/multiclusterhub.yaml || echo "   ⚠️  MultiClusterHub failed to apply"
fi

# Wait for Crossplane operator CRDs
echo "   ⏳ Waiting for Crossplane operator CRDs..."
crossplane_crd_wait=120
crossplane_elapsed=0
while [[ $crossplane_elapsed -lt $crossplane_crd_wait ]]; do
    if oc get crd providers.pkg.crossplane.io >/dev/null 2>&1; then
        echo "   ✅ Crossplane operator CRDs are ready"
        break
    fi
    echo "   ⏳ Waiting for Crossplane CRDs... (${crossplane_elapsed}s elapsed)"
    sleep 10
    crossplane_elapsed=$((crossplane_elapsed + 10))
done

if [[ $crossplane_elapsed -ge $crossplane_crd_wait ]]; then
    echo "   ⚠️  Timeout waiting for Crossplane CRDs, skipping Provider installation..."
else
    echo "   ☁️  Applying Crossplane AWS Provider..."
    cd "${SCRIPT_DIR}"
    oc apply -f crossplane/provider.yaml || echo "   ⚠️  Crossplane Provider failed to apply"
fi

echo ""

# Step 5: Wait for Provider installation and apply ProviderConfig
echo "🔧 Step 5: Waiting for AWS Provider installation and applying ProviderConfig..."
# Wait for Provider to be installed and healthy
echo "   ⏳ Waiting for AWS Provider to be installed..."
provider_install_wait=180
provider_install_elapsed=0
while [[ $provider_install_elapsed -lt $provider_install_wait ]]; do
    provider_status=$(oc get providers provider-aws-iam -o jsonpath='{.status.conditions[?(@.type=="Healthy")].status}' 2>/dev/null || echo "False")
    if [[ "$provider_status" == "True" ]]; then
        echo "   ✅ AWS Provider is healthy and installed"
        break
    fi
    echo "   ⏳ Waiting for AWS Provider to be healthy... (${provider_install_elapsed}s elapsed)"
    sleep 15
    provider_install_elapsed=$((provider_install_elapsed + 15))
done

if [[ $provider_install_elapsed -ge $provider_install_wait ]]; then
    echo "   ⚠️  Timeout waiting for AWS Provider to be healthy, checking for CRDs anyway..."
fi

echo "   ⏳ Waiting for AWS provider CRDs..."

# Wait for the AWS provider CRDs to be available
provider_crd_wait=90
provider_crd_elapsed=0
while [[ $provider_crd_elapsed -lt $provider_crd_wait ]]; do
    if oc get crd providerconfigs.aws.upbound.io >/dev/null 2>&1; then
        echo "   ✅ AWS provider CRDs are ready"
        break
    fi
    echo "   ⏳ Waiting for AWS provider CRDs... (${provider_crd_elapsed}s elapsed)"
    sleep 10
    provider_crd_elapsed=$((provider_crd_elapsed + 10))
done

if [[ $provider_crd_elapsed -ge $provider_crd_wait ]]; then
    echo "   ⚠️  Timeout waiting for AWS provider CRDs, trying ProviderConfig anyway..."
fi

cd "${SCRIPT_DIR}"
echo "   Applying ProviderConfig..."
oc apply -f crossplane/providerconfig.yaml || echo "   ProviderConfig already exists or failed to apply"

echo ""

# Step 6: Enable Console Plugins
echo "🎮 Step 6: Enabling console plugins..."

# Get current plugins
current_plugins=$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins[*]}' 2>/dev/null || echo "")

plugins_to_add=()

# Check GitOps operator and plugin
if oc get csv -n openshift-gitops --no-headers 2>/dev/null | grep -q "openshift-gitops-operator.*Succeeded"; then
    if oc get consoleplugin gitops-plugin >/dev/null 2>&1; then
        if ! echo "$current_plugins" | grep -q "gitops-plugin"; then
            plugins_to_add+=("gitops-plugin")
            echo "   📌 GitOps operator installed - will enable gitops-plugin"
        else
            echo "   ✅ GitOps plugin already enabled"
        fi
    else
        echo "   ⚠️  GitOps operator installed but plugin not found yet"
    fi
else
    echo "   ℹ️  GitOps operator not installed - skipping gitops-plugin"
fi

# Check Pipelines operator and plugin
if oc get csv -n openshift-pipelines --no-headers 2>/dev/null | grep -q "openshift-pipelines-operator.*Succeeded"; then
    if oc get consoleplugin pipelines-console-plugin >/dev/null 2>&1; then
        if ! echo "$current_plugins" | grep -q "pipelines-console-plugin"; then
            plugins_to_add+=("pipelines-console-plugin")
            echo "   📌 Pipelines operator installed - will enable pipelines-console-plugin"
        else
            echo "   ✅ Pipelines plugin already enabled"
        fi
    else
        echo "   ⚠️  Pipelines operator installed but plugin not found yet"
    fi
else
    echo "   ℹ️  Pipelines operator not installed - skipping pipelines-console-plugin"
fi

# Enable plugins if any need to be added
if [[ ${#plugins_to_add[@]} -gt 0 ]]; then
    echo "   🔧 Updating console configuration..."

    # Get current plugins as JSON array
    current_plugins_json=$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null || echo "[]")

    # Add new plugins to the list
    for plugin in "${plugins_to_add[@]}"; do
        current_plugins_json=$(echo "$current_plugins_json" | jq --arg plugin "$plugin" '. + [$plugin] | unique')
    done

    # Apply the updated plugin list
    oc patch console.operator.openshift.io cluster --type merge -p "{\"spec\":{\"plugins\":$current_plugins_json}}"

    echo "   ✅ Console plugins updated"
    echo "   💡 Console plugins may take a few minutes to appear in the web console"
else
    echo "   ✅ No new console plugins to enable"
fi

echo ""

# Step 7: Verification
echo "🔍 Step 7: Final verification..."

echo "   📊 Operator Status:"
# Check key operators in their primary namespaces
cert_manager_status=$(oc get csv -n cert-manager --no-headers 2>/dev/null | grep cert-manager-operator | awk '{print $1 " - " $NF}' || echo "Not Found")
gitops_status=$(oc get csv -n openshift-gitops --no-headers 2>/dev/null | grep openshift-gitops-operator | awk '{print $1 " - " $NF}' || echo "Not Found")
pipelines_status=$(oc get csv -n openshift-pipelines --no-headers 2>/dev/null | grep openshift-pipelines-operator-rh | awk '{print $1 " - " $NF}' || echo "Not Found")
acm_status=$(oc get csv -n open-cluster-management --no-headers 2>/dev/null | grep advanced-cluster-management | awk '{print $1 " - " $NF}' || echo "Not Found")
rhsso_status=$(oc get csv -n partner-labs-auth --no-headers 2>/dev/null | grep rhsso-operator | awk '{print $1 " - " $NF}' || echo "Not Found")

echo "     🔒 cert-manager: $cert_manager_status"
echo "     📦 gitops: $gitops_status"
echo "     🔄 pipelines: $pipelines_status"
echo "     🌐 acm: $acm_status"
echo "     🔐 rhsso: $rhsso_status"

echo ""
echo "   ☁️  Crossplane Status:"
provider_status=$(oc get providers --no-headers 2>/dev/null | wc -l | tr -d ' \n')
providerconfig_status=$(oc get providerconfig.aws.upbound.io --no-headers 2>/dev/null | wc -l | tr -d ' \n')
echo "     📦 Providers: $provider_status"
echo "     🔑 ProviderConfigs: $providerconfig_status"

echo ""
echo "   🌐 ACM Status:"
mch_status=$(oc get multiclusterhub -n open-cluster-management --no-headers 2>/dev/null | awk '{print $2}' || echo "Not Found")
echo "     🏗️  MultiClusterHub: $mch_status"

echo ""
echo "   📦 ArgoCD Status:"
argocd_status=$(oc get argocds -n openshift-gitops --no-headers 2>/dev/null | wc -l | tr -d ' \n')
echo "     🚀 ArgoCD Instances: $argocd_status"

echo ""
echo "   🎮 Console Plugin Status:"
enabled_plugins=$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins[*]}' 2>/dev/null | tr ' ' '\n' | grep -E "(gitops|pipelines)" | sort || echo "")
if [[ -n "$enabled_plugins" ]]; then
    echo "$enabled_plugins" | while read plugin; do
        echo "     ✅ $plugin"
    done
else
    echo "     ⚠️  No GitOps or Pipelines console plugins enabled"
fi

echo ""
echo "🎉 Hub cluster installation completed successfully!"
echo ""
echo "🔍 Next Steps:"
echo "   • Check OpenShift console for operator tabs (Pipelines, GitOps, etc.)"
echo "   • Configure ArgoCD applications for fleet management"
echo "   • Set up ACM cluster import/provisioning"
echo "   • Configure Crossplane compositions for infrastructure"
echo ""
echo "📋 Quick Status Check:"
echo "   oc get csv -A | grep -E '(cert-manager|gitops|pipelines|advanced-cluster-management)'"
echo "   oc get providers"
echo "   oc get multiclusterhub -A"