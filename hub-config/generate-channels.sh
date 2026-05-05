#!/bin/bash

# Generate dynamic channel configuration for operators
# This script queries the cluster for available operator channels
# and updates the subscription files with the latest available channels

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔍 Querying cluster for available operator channels..."

# Function to get the latest channel for a package
get_latest_channel() {
    local package_name="$1"
    local filter_pattern="${2:-}"

    echo "  📦 Checking channels for ${package_name}..." >&2

    local channels
    channels=$(oc get packagemanifests "${package_name}" -n openshift-marketplace -o jsonpath='{.status.channels[*].name}' 2>/dev/null || echo "")

    if [[ -z "$channels" ]]; then
        echo "    ❌ Package ${package_name} not found" >&2
        return 1
    fi

    echo "    📋 Available channels: ${channels}" >&2

    # If filter pattern provided, filter channels
    if [[ -n "$filter_pattern" ]]; then
        channels=$(echo "$channels" | tr ' ' '\n' | grep -E "$filter_pattern" | tr '\n' ' ')
        echo "    🎯 Filtered channels: ${channels}" >&2
    fi

    # Get the latest/highest version channel
    local latest_channel
    latest_channel=$(echo "$channels" | tr ' ' '\n' | sort -V | tail -1)

    if [[ -n "$latest_channel" ]]; then
        echo "    ✅ Selected channel: ${latest_channel}" >&2
        echo "$latest_channel"
    else
        echo "    ❌ No suitable channel found" >&2
        return 1
    fi
}

# Function to update channel in subscription file
update_channel() {
    local file="$1"
    local placeholder="$2"
    local channel="$3"

    if [[ -f "$file" ]]; then
        sed -i.bak "s/${placeholder}/${channel}/g" "$file"
        echo "    📝 Updated ${file}: ${placeholder} → ${channel}"
        rm -f "${file}.bak"
    else
        echo "    ❌ File not found: ${file}"
        return 1
    fi
}

# Check cluster connectivity
if ! oc cluster-info >/dev/null 2>&1; then
    echo "❌ Error: Not connected to an OpenShift cluster"
    echo "   Please login with 'oc login' first"
    exit 1
fi

echo "✅ Connected to cluster: $(oc config current-context)"
echo ""

# Query channels for each operator
echo "🔍 Discovering operator channels..."

# cert-manager
echo "🔒 cert-manager operator:"
CERT_MANAGER_CHANNEL=$(get_latest_channel "openshift-cert-manager-operator" "stable-v")
update_channel "${SCRIPT_DIR}/cert-manager/subscription.yaml" "CERT_MANAGER_CHANNEL" "$CERT_MANAGER_CHANNEL"
echo ""

# Advanced Cluster Management
echo "🌐 Advanced Cluster Management:"
ACM_CHANNEL=$(get_latest_channel "advanced-cluster-management" "release-")
update_channel "${SCRIPT_DIR}/acm/subscription.yaml" "ACM_CHANNEL" "$ACM_CHANNEL"
echo ""

# OpenShift GitOps
echo "📦 OpenShift GitOps:"
GITOPS_CHANNEL=$(get_latest_channel "openshift-gitops-operator" "gitops-")
update_channel "${SCRIPT_DIR}/argocd/subscription.yaml" "GITOPS_CHANNEL" "$GITOPS_CHANNEL"
echo ""

# OpenShift Pipelines
echo "🔄 OpenShift Pipelines:"
PIPELINES_CHANNEL=$(get_latest_channel "openshift-pipelines-operator-rh" "")
update_channel "${SCRIPT_DIR}/tekton/subscription.yaml" "PIPELINES_CHANNEL" "$PIPELINES_CHANNEL"
echo ""

# Generate summary
echo "📊 Channel Updates Summary:"
echo "  🔒 cert-manager: ${CERT_MANAGER_CHANNEL}"
echo "  🌐 ACM: ${ACM_CHANNEL}"
echo "  📦 GitOps: ${GITOPS_CHANNEL}"
echo "  🔄 Pipelines: ${PIPELINES_CHANNEL}"
echo ""

echo "🎉 All subscription channels updated successfully!"
echo "💡 You can now run: oc apply -k ."
echo ""
echo "🔄 To update channels in the future, run this script again."
echo "📝 Note: Original files are backed up with .bak extension"