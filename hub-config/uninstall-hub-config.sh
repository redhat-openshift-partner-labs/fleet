#!/bin/bash

# Graceful uninstallation of hub-config
# Removes resources in proper order to avoid stuck namespaces

set -euo pipefail

echo "🗑️  Hub Cluster Operator Uninstallation"
echo "======================================"

# Check cluster connectivity
if ! oc cluster-info >/dev/null 2>&1; then
    echo "❌ Error: Not connected to an OpenShift cluster"
    echo "   Please login with 'oc login' first"
    exit 1
fi

echo "✅ Connected to cluster: $(oc config current-context)"
echo ""

# Confirmation prompt
echo "⚠️  WARNING: This will remove ALL hub cluster operators and configurations!"
echo "   The following will be deleted:"
echo "   • Advanced Cluster Management (ACM)"
echo "   • ArgoCD/OpenShift GitOps"
echo "   • Tekton/OpenShift Pipelines"
echo "   • cert-manager"
echo "   • Crossplane and providers"
echo "   • All related namespaces and RBAC"
echo ""
read -p "Are you sure you want to proceed? (type 'yes' to continue): " confirmation

if [[ "$confirmation" != "yes" ]]; then
    echo "❌ Uninstallation cancelled"
    exit 0
fi

echo ""
echo "🧹 Starting graceful uninstallation..."

# Pre-Step: Proactively remove validating webhooks to prevent cleanup blocks
echo "🔓 Pre-cleanup: Removing validating webhooks to prevent blocking..."
echo "   Removing ACM and ArgoCD validating webhooks..."
oc get validatingwebhookconfiguration -o name 2>/dev/null | grep -E "(cluster-management|multicluster|gitops|argocd)" | xargs -r oc delete --ignore-not-found=true >/dev/null 2>&1 || true
echo "   ✅ Validating webhooks removed proactively"

echo ""

# Step 1: Delete ACM Custom Resources
echo "1️⃣  Removing ACM Custom Resources..."

# First try graceful deletion
echo "   Attempting graceful MultiClusterHub deletion..."
oc delete multiclusterhub --all --all-namespaces --ignore-not-found=true --timeout=60s || echo "   Graceful deletion timed out or failed"

# Check for stuck MultiClusterHubs and force remove finalizers
stuck_mchs=$(oc get multiclusterhub --all-namespaces --no-headers 2>/dev/null | grep -v "^$" || echo "")
if [[ -n "$stuck_mchs" ]]; then
    echo "   Force removing stuck MultiClusterHub finalizers..."
    echo "$stuck_mchs" | while read ns mch_name status age version desired_version; do
        echo "     Removing finalizers from MultiClusterHub $mch_name in $ns..."
        oc patch multiclusterhub "$mch_name" -n "$ns" --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    done
fi

# Also handle MultiClusterEngine
echo "   Attempting graceful MultiClusterEngine deletion..."
oc delete multiclusterengine --all --ignore-not-found=true --timeout=60s || echo "   Graceful deletion timed out or failed"

stuck_mces=$(oc get multiclusterengine --no-headers 2>/dev/null | grep -v "^$" || echo "")
if [[ -n "$stuck_mces" ]]; then
    echo "   Force removing stuck MultiClusterEngine finalizers..."
    echo "$stuck_mces" | while read mce_name status age version desired_version; do
        echo "     Removing finalizers from MultiClusterEngine $mce_name..."
        oc patch multiclusterengine "$mce_name" --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    done
fi

echo "   ✅ ACM Custom Resources removed"

# Step 2: Delete Crossplane Custom Resources
echo ""
echo "2️⃣  Removing Crossplane Custom Resources..."
oc delete providers --all --ignore-not-found=true --timeout=60s || echo "   No Providers found"
oc delete providerconfig.aws.upbound.io --all --ignore-not-found=true --timeout=60s || echo "   No ProviderConfigs found"
echo "   ✅ Crossplane CRs removed"

# Step 3: Delete Crossplane Installation Job
echo ""
echo "3️⃣  Removing Crossplane Installation Job..."
oc delete job crossplane-helm-installer -n crossplane-system --ignore-not-found=true --timeout=30s || echo "   No Crossplane job found"
echo "   ✅ Crossplane job removed"

# Step 4: Wait for CR cleanup
echo ""
echo "4️⃣  Waiting for custom resources to clean up..."
sleep 10

# Step 5: Delete Operator Subscriptions
echo ""
echo "5️⃣  Removing Operator Subscriptions..."
subscriptions=("advanced-cluster-management" "cert-manager" "openshift-gitops-operator" "openshift-pipelines-operator" "rhsso-operator")

for sub in "${subscriptions[@]}"; do
    echo "   Removing subscription: $sub"
    # Use correct subscription resource type to avoid CRD conflicts
    oc delete subscription.operators.coreos.com "$sub" -n openshift-operators --ignore-not-found=true --timeout=30s || echo "     Not found in openshift-operators"
    oc delete subscription.operators.coreos.com "$sub" -n open-cluster-management --ignore-not-found=true --timeout=30s || echo "     Not found in open-cluster-management"
    oc delete subscription.operators.coreos.com "$sub" -n cert-manager-operator --ignore-not-found=true --timeout=30s || echo "     Not found in cert-manager-operator"
    oc delete subscription.operators.coreos.com "$sub" -n partner-labs-auth --ignore-not-found=true --timeout=30s || echo "     Not found in partner-labs-auth"
done

# Delete operator groups
oc delete operatorgroup open-cluster-management -n open-cluster-management --ignore-not-found=true --timeout=30s || echo "   No ACM OperatorGroup found"
oc delete operatorgroup cert-manager-operator -n cert-manager-operator --ignore-not-found=true --timeout=30s || echo "   No cert-manager OperatorGroup found"
oc delete operatorgroup partner-labs-auth -n partner-labs-auth --ignore-not-found=true --timeout=30s || echo "   No partner-labs-auth OperatorGroup found"

echo "   ✅ Subscriptions removed"

# Step 5.5: Delete InstallPlans (NEW - was missing)
echo ""
echo "5️⃣.5️⃣ Removing InstallPlans..."
echo "   Deleting all InstallPlans in openshift-operators namespace..."
oc delete installplan --all -n openshift-operators --ignore-not-found=true --timeout=30s || echo "   No InstallPlans found"
echo "   Deleting all InstallPlans in open-cluster-management namespace..."
oc delete installplan --all -n open-cluster-management --ignore-not-found=true --timeout=30s || echo "   No InstallPlans found"
echo "   Deleting all InstallPlans in cert-manager-operator namespace..."
oc delete installplan --all -n cert-manager-operator --ignore-not-found=true --timeout=30s || echo "   No InstallPlans found"
echo "   Deleting all InstallPlans in partner-labs-auth namespace..."
oc delete installplan --all -n partner-labs-auth --ignore-not-found=true --timeout=30s || echo "   No InstallPlans found"
echo "   ✅ InstallPlans removed"

# Step 6: Delete ClusterServiceVersions
echo ""
echo "6️⃣  Removing ClusterServiceVersions (operators)..."
csv_patterns=("cert-manager-operator" "openshift-gitops-operator" "openshift-pipelines-operator" "advanced-cluster-management" "rhsso-operator")

for csv_pattern in "${csv_patterns[@]}"; do
    echo "   Removing CSVs matching: $csv_pattern"
    oc delete csv --all-namespaces --ignore-not-found=true --timeout=60s -l "operators.coreos.com/${csv_pattern}" || true

    # Also try direct deletion by name pattern
    csvs=$(oc get csv --all-namespaces --no-headers 2>/dev/null | grep "$csv_pattern" | awk '{print $1 " " $2}' || echo "")
    if [[ -n "$csvs" ]]; then
        echo "$csvs" | while read ns csv_name; do
            echo "     Deleting CSV: $csv_name in namespace $ns"
            oc delete csv "$csv_name" -n "$ns" --ignore-not-found=true --timeout=30s || true
        done
    fi
done

echo "   ✅ CSVs removed"

# Step 7: Delete RBAC Resources
echo ""
echo "7️⃣  Removing RBAC Resources..."
rbac_resources=("crossplane-installer" "crossplane-privileged-scc")

for resource in "${rbac_resources[@]}"; do
    echo "   Removing ClusterRole/ClusterRoleBinding: $resource"
    oc delete clusterrole "$resource" --ignore-not-found=true --timeout=30s || true
    oc delete clusterrolebinding "$resource" --ignore-not-found=true --timeout=30s || true
    oc delete serviceaccount "$resource" -n crossplane-system --ignore-not-found=true --timeout=30s || true
done

echo "   ✅ RBAC resources removed"

# Step 8: Wait for operator cleanup
echo ""
echo "8️⃣  Waiting for operators to finish cleanup..."
max_wait=180 # 3 minutes
wait_time=0
check_interval=10

while [[ $wait_time -lt $max_wait ]]; do
    remaining_csvs=$(oc get csv --all-namespaces --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)" | wc -l | tr -d ' \n' || echo "0")

    if [[ $remaining_csvs -eq 0 ]]; then
        echo "   ✅ All operators cleaned up"
        break
    fi

    echo "   ⏳ Waiting for $remaining_csvs operators to finish cleanup..."
    sleep $check_interval
    wait_time=$((wait_time + check_interval))
done

if [[ $wait_time -ge $max_wait ]]; then
    echo "   ⚠️  Timeout waiting for operators to cleanup. Continuing with namespace removal..."
    echo "   Remaining operators:"
    oc get csv --all-namespaces --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)" || echo "     None found"
fi

# Step 8.5: Disable Console Plugins
echo ""
echo "8️⃣.5️⃣ Disabling console plugins..."

# Get current plugins
current_plugins=$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins[*]}' 2>/dev/null || echo "")

# Define plugins to remove based on our operators
plugins_to_remove=("gitops-plugin" "pipelines-console-plugin")

# Check which plugins are currently enabled and need removal
plugins_found=()
for plugin in "${plugins_to_remove[@]}"; do
    if echo "$current_plugins" | grep -q "$plugin"; then
        plugins_found+=("$plugin")
        echo "   🔌 Will disable plugin: $plugin"
    fi
done

# Remove plugins if any are found
if [[ ${#plugins_found[@]} -gt 0 ]]; then
    echo "   🔧 Updating console configuration..."

    # Get current plugins as JSON array
    current_plugins_json=$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' 2>/dev/null || echo "[]")

    # Remove our plugins from the list
    for plugin in "${plugins_found[@]}"; do
        current_plugins_json=$(echo "$current_plugins_json" | jq --arg plugin "$plugin" 'map(select(. != $plugin))')
    done

    # Apply the updated plugin list
    oc patch console.operator.openshift.io cluster --type merge -p "{\"spec\":{\"plugins\":$current_plugins_json}}" || echo "   Failed to update console plugins (continuing)"

    echo "   ✅ Console plugins updated"
else
    echo "   ✅ No hub-config console plugins currently enabled"
fi

echo ""

# Step 9: Delete Namespaces
echo ""
echo "9️⃣  Removing Namespaces..."
namespaces=("cert-manager" "crossplane-system" "multicluster-engine" "open-cluster-management" "openshift-gitops" "openshift-pipelines" "cert-manager-operator" "partner-labs-auth")

for ns in "${namespaces[@]}"; do
    echo "   Removing namespace: $ns"
    oc delete namespace "$ns" --ignore-not-found=true --timeout=60s || echo "     Failed to delete $ns (may need manual cleanup)"
done

# Step 10: Final cleanup check
echo ""
echo "🔟 Final cleanup verification..."
sleep 5

stuck_namespaces=()
for ns in "${namespaces[@]}"; do
    if oc get namespace "$ns" >/dev/null 2>&1; then
        ns_status=$(oc get namespace "$ns" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
        if [[ "$ns_status" == "Terminating" ]]; then
            stuck_namespaces+=("$ns")
        fi
    fi
done

if [[ ${#stuck_namespaces[@]} -gt 0 ]]; then
    echo ""
    echo "⚠️  Some namespaces are stuck in Terminating state:"
    for ns in "${stuck_namespaces[@]}"; do
        echo "     🔒 $ns"
    done
    echo ""
    echo "💡 To force cleanup stuck namespaces:"
    echo "   for ns in ${stuck_namespaces[*]}; do"
    echo "     kubectl patch namespace \$ns --type merge -p '{\"spec\":{\"finalizers\":[]}}'"
    echo "   done"
else
    echo "   ✅ All namespaces removed cleanly"
fi

echo ""

# Step 11: Force cleanup of stuck ACM resources
echo ""
echo "🔟 Step 11: Force cleanup of any stuck ACM resources..."

# Remove ACM validating webhooks that can block cleanup
echo "   Removing ACM validating webhooks..."
oc get validatingwebhookconfiguration -o name 2>/dev/null | grep -E "(cluster-management|multicluster)" | xargs -r oc delete --ignore-not-found=true >/dev/null 2>&1 || true

# Force cleanup stuck MultiClusterHub
if oc get multiclusterhub --all-namespaces --no-headers 2>/dev/null | grep -q .; then
    echo "   Force removing stuck MultiClusterHub resources..."
    for mch in $(oc get multiclusterhub --all-namespaces --no-headers -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name 2>/dev/null | awk '{print $1":"$2}'); do
        ns=$(echo $mch | cut -d: -f1)
        name=$(echo $mch | cut -d: -f2)
        echo "     Removing finalizers from MultiClusterHub $name in $ns..."
        oc patch multiclusterhub "$name" -n "$ns" --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    done
fi

# Force cleanup stuck MultiClusterEngine
if oc get multiclusterengine --no-headers 2>/dev/null | grep -q .; then
    echo "   Force removing stuck MultiClusterEngine resources..."
    for mce in $(oc get multiclusterengine --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null); do
        echo "     Removing finalizers from MultiClusterEngine $mce..."
        oc patch multiclusterengine "$mce" --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    done
fi

echo "   ✅ ACM resources force cleanup completed"

# Step 12: Force cleanup of stuck ArgoCD resources
echo ""
echo "1️⃣2️⃣ Step 12: Force cleanup of any stuck ArgoCD resources..."

for ns in $(oc get namespaces --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null | grep -E "(openshift-gitops|argocd)"); do
    if oc get argocd -n "$ns" --no-headers 2>/dev/null | grep -q .; then
        echo "   Force removing ArgoCD resources in namespace $ns..."
        for argocd in $(oc get argocd -n "$ns" --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null); do
            echo "     Removing finalizers from ArgoCD $argocd..."
            oc patch argocd "$argocd" -n "$ns" --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
        done
    fi
done

echo "   ✅ ArgoCD resources force cleanup completed"

# Step 13: Force cleanup terminating namespaces
echo ""
echo "1️⃣3️⃣ Step 13: Force cleanup of any terminating namespaces..."

terminating_namespaces=$(oc get namespaces --no-headers 2>/dev/null | grep "Terminating" | awk '{print $1}' || echo "")
if [[ -n "$terminating_namespaces" ]]; then
    echo "   Found terminating namespaces: $terminating_namespaces"
    for ns in $terminating_namespaces; do
        echo "     Force finalizing namespace: $ns"
        # Try to remove finalizers from the namespace
        oc get namespace "$ns" -o json 2>/dev/null | jq '.spec.finalizers = []' | oc replace --raw "/api/v1/namespaces/$ns/finalize" -f - >/dev/null 2>&1 || true
    done

    # Wait a moment and check again
    sleep 5
    remaining_terminating=$(oc get namespaces --no-headers 2>/dev/null | grep "Terminating" | awk '{print $1}' || echo "")
    if [[ -n "$remaining_terminating" ]]; then
        echo "   ⚠️  Still terminating: $remaining_terminating"
        echo "   These may need manual intervention if they persist"
    else
        echo "   ✅ All terminating namespaces resolved"
    fi
else
    echo "   ✅ No terminating namespaces found"
fi

echo ""

# Step 14: Final comprehensive verification
echo "🔍 Step 14: Final comprehensive verification..."

echo "   📊 Checking for any remaining resources..."

# Check operators
remaining_resources=$(oc get csv --all-namespaces --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)" | wc -l | tr -d ' \n' || echo "0")
remaining_providers=$(oc get providers --no-headers 2>/dev/null | wc -l | tr -d ' \n' || echo "0")
remaining_mch=$(oc get multiclusterhub --all-namespaces --no-headers 2>/dev/null | wc -l | tr -d ' \n' || echo "0")
remaining_mce=$(oc get multiclusterengine --no-headers 2>/dev/null | wc -l | tr -d ' \n' || echo "0")
remaining_argocd=$(oc get argocd --all-namespaces --no-headers 2>/dev/null | wc -l | tr -d ' \n' || echo "0")
# FIX: Use correct subscription resource type to avoid CRD conflicts
remaining_subscriptions=$(oc get subscriptions.operators.coreos.com --all-namespaces --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management)" | wc -l | tr -d ' \n' || echo "0")
# NEW: Add InstallPlan verification (was missing completely)
remaining_installplans=$(oc get installplans --all-namespaces --no-headers 2>/dev/null | wc -l | tr -d ' \n' || echo "0")
remaining_terminating=$(oc get namespaces --no-headers 2>/dev/null | grep "Terminating" | wc -l | tr -d ' \n' || echo "0")

echo ""
echo "📊 Final Cleanup Summary:"
echo "   • Operator CSVs: $remaining_resources"
echo "   • Crossplane providers: $remaining_providers"
echo "   • MultiClusterHubs: $remaining_mch"
echo "   • MultiClusterEngines: $remaining_mce"
echo "   • ArgoCD instances: $remaining_argocd"
echo "   • Operator subscriptions: $remaining_subscriptions"
echo "   • InstallPlans: $remaining_installplans"
echo "   • Terminating namespaces: $remaining_terminating"

total_remaining=$((remaining_resources + remaining_providers + remaining_mch + remaining_mce + remaining_argocd + remaining_subscriptions + remaining_installplans + remaining_terminating))

if [[ $total_remaining -eq 0 ]]; then
    echo ""
    echo "🌟 Complete success! All hub cluster components fully removed."
    echo "🎉 Hub cluster uninstallation completed successfully!"
else
    echo ""
    echo "⚠️  Some resources may still exist ($total_remaining total). Manual commands for investigation:"
    echo "   oc get csv -A | grep -E '(cert-manager|gitops|pipelines|advanced-cluster-management)'"
    echo "   oc get providers"
    echo "   oc get multiclusterhub -A"
    echo "   oc get multiclusterengine"
    echo "   oc get argocd -A"
    echo "   oc get subscriptions.operators.coreos.com -A | grep -E '(cert-manager|gitops|pipelines|advanced-cluster-management)'"
    echo "   oc get installplans -A"
    echo "   oc get namespaces | grep Terminating"

    echo ""
    echo "🎉 Hub cluster uninstallation completed (with $total_remaining resources to check manually)."
fi