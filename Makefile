.PHONY: lint lint-yaml lint-tekton validate hub-install hub-uninstall hub-channels hub-status hub-check

# Existing linting targets
lint:
	tox

lint-yaml:
	tox -e yamllint

lint-tekton:
	tox -e tekton-lint

validate:
	tox -e validate-kustomize

# Hub config management targets
hub-install: ## Install all hub cluster operators with automated sequencing
	@echo "🚀 Starting hub cluster operator installation..."
	@cd hub-config && KUBECONFIG="$$KUBECONFIG" ./install-hub-config.sh

hub-uninstall: ## Gracefully remove all hub cluster operators and resources
	@echo "🗑️ Starting hub cluster operator uninstallation..."
	@cd hub-config && KUBECONFIG="$$KUBECONFIG" ./uninstall-hub-config.sh

hub-channels: ## Generate and update dynamic operator channels
	@echo "📡 Updating operator channels..."
	@if ! command -v oc >/dev/null 2>&1; then \
		echo "❌ Error: oc command not found. Please install OpenShift CLI."; \
		exit 1; \
	fi
	@if [ -z "$$KUBECONFIG" ] && ! oc cluster-info >/dev/null 2>&1; then \
		echo "❌ Error: Not connected to OpenShift cluster."; \
		echo "   Set KUBECONFIG environment variable or run 'oc login' first."; \
		echo "   Example: export KUBECONFIG=/Users/yoza/Projects/fleet/yash-hub-cluster-kubeconfig.yaml"; \
		exit 1; \
	fi
	@cd hub-config && KUBECONFIG="$$KUBECONFIG" ./generate-channels.sh

hub-status: ## Check status of hub cluster operators
	@echo "📊 Hub Cluster Operator Status"
	@echo "============================="
	@echo ""
	@if ! command -v oc >/dev/null 2>&1; then \
		echo "❌ Error: oc command not found. Please install OpenShift CLI."; \
		exit 1; \
	fi
	@if [ -z "$$KUBECONFIG" ] && ! oc cluster-info >/dev/null 2>&1; then \
		echo "❌ Error: Not connected to OpenShift cluster."; \
		echo "   Set KUBECONFIG environment variable or run 'oc login' first."; \
		echo "   Example: export KUBECONFIG=/Users/yoza/Projects/fleet/yash-hub-cluster-kubeconfig.yaml"; \
		exit 1; \
	fi
	@echo "🔍 Operator Status:"
	@oc get csv -A --no-headers 2>/dev/null | grep -E "(cert-manager|gitops|pipelines|advanced-cluster-management|rhsso)" | while read line; do \
		echo "  ✅ $$line"; \
	done || echo "  ❌ No operators found"
	@echo ""
	@echo "☁️  Crossplane Status:"
	@provider_count=$$(oc get providers --no-headers 2>/dev/null | wc -l || echo "0"); \
	providerconfig_count=$$(oc get providerconfig.aws.upbound.io --no-headers 2>/dev/null | wc -l || echo "0"); \
	echo "  📦 Providers: $$provider_count"; \
	echo "  🔑 ProviderConfigs: $$providerconfig_count"
	@echo ""
	@echo "🌐 ACM Status:"
	@mch_status=$$(oc get multiclusterhub -n open-cluster-management --no-headers 2>/dev/null | awk '{print $$2}' || echo "Not Found"); \
	echo "  🏗️  MultiClusterHub: $$mch_status"
	@echo ""
	@echo "📦 ArgoCD Status:"
	@argocd_count=$$(oc get argocds -n openshift-gitops --no-headers 2>/dev/null | wc -l || echo "0"); \
	echo "  🚀 ArgoCD Instances: $$argocd_count"
	@echo ""
	@echo "🎮 Console Plugin Status:"
	@enabled_plugins=$$(oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins[*]}' 2>/dev/null | tr ' ' '\n' | grep -E "(gitops|pipelines)" | sort || echo ""); \
	if [ -n "$$enabled_plugins" ]; then \
		echo "$$enabled_plugins" | while read plugin; do \
			echo "  ✅ $$plugin"; \
		done; \
	else \
		echo "  ⚠️  No GitOps or Pipelines console plugins enabled"; \
	fi

hub-check: ## Check hub-config prerequisites and cluster connection
	@echo "🔍 Checking hub-config prerequisites..."
	@if command -v oc >/dev/null 2>&1; then \
		echo "  ✅ OpenShift CLI (oc) found"; \
	else \
		echo "  ❌ OpenShift CLI (oc) not found"; \
		exit 1; \
	fi
	@if oc cluster-info >/dev/null 2>&1; then \
		cluster_info=$$(oc config current-context 2>/dev/null || echo "unknown"); \
		echo "  ✅ Connected to cluster: $$cluster_info"; \
	else \
		echo "  ❌ Not connected to OpenShift cluster"; \
		echo "     Run 'oc login <cluster-url>' first"; \
		exit 1; \
	fi
	@if [ -f "hub-config/generate-channels.sh" ] && [ -x "hub-config/generate-channels.sh" ]; then \
		echo "  ✅ generate-channels.sh is executable"; \
	else \
		echo "  ❌ hub-config/generate-channels.sh not found or not executable"; \
		exit 1; \
	fi
	@if [ -f "hub-config/install-hub-config.sh" ] && [ -x "hub-config/install-hub-config.sh" ]; then \
		echo "  ✅ install-hub-config.sh is executable"; \
	else \
		echo "  ❌ hub-config/install-hub-config.sh not found or not executable"; \
		exit 1; \
	fi
	@if [ -f "hub-config/uninstall-hub-config.sh" ] && [ -x "hub-config/uninstall-hub-config.sh" ]; then \
		echo "  ✅ uninstall-hub-config.sh is executable"; \
	else \
		echo "  ❌ hub-config/uninstall-hub-config.sh not found or not executable"; \
		exit 1; \
	fi
	@echo "🎉 All hub-config prerequisites met"
