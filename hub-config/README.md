# Hub Operators

This guide describes how to install, verify, change and uninstall the hub operators that `hub-config/` defines.

It is one part of the hub setup. [docs/hub-setup.md](../docs/hub-setup.md) gives the whole setup in order: these operators, then the pipelines, their configuration and their Secrets.

## Components

| Directory | Component | Installed as | Namespace | Channel or version |
|---|---|---|---|---|
| `acm/` | Advanced Cluster Management with Hive | Operator `advanced-cluster-management` and the MultiClusterHub `multiclusterhub` | `open-cluster-management` | `release-2.16` |
| `argocd/` | OpenShift GitOps (ArgoCD) | Operator `openshift-gitops-operator` | `openshift-operators` | `gitops-1.20` |
| `cert-manager/` | cert-manager | Operator `openshift-cert-manager-operator` with its own OperatorGroup | `cert-manager-operator` | `stable-v1.19` |
| `tekton/` | OpenShift Pipelines (Tekton) | Operator `openshift-pipelines-operator-rh` | `openshift-operators` | `pipelines-1.22` |
| `partner-labs-auth/` | Red Hat Single Sign-On (Keycloak) | Operator `rhsso-operator` with its own OperatorGroup | `partner-labs-auth` | `stable` |
| `crossplane/` | Crossplane | Helm chart `crossplane`, installed by the Job `crossplane-helm-installer`; Provider `provider-aws-iam` | `crossplane-system` | Chart `2.2.0`, provider `v1.7.0` |

`namespaces.yaml` creates the namespaces. [docs/architecture.md](../docs/architecture.md#components) describes what each component does in the system.

The directory installs the RH-SSO operator only. The Keycloak instance and its realm are created by hand; see [docs/hub-setup.md](../docs/hub-setup.md#5-set-up-keycloak).

## Install

Prerequisites: `oc` logged in to the hub as a cluster administrator, and `jq`.

From the root of the repository:

```bash
make hub-install
```

The target runs `hub-config/install-hub-config.sh`. The script does this:

| Step | Action | Waits up to |
|---|---|---|
| 1 | Applies the namespaces, the OperatorGroups and Subscriptions of the five operators, and the Crossplane RBAC, Helm Job and SCC binding | |
| 2 | Waits until the five operators report `Succeeded` and the Job `crossplane-helm-installer` is complete. Exits with an error on a failed operator, a failed Job or the timeout. | 600 seconds |
| 3 | Waits for the ACM and Crossplane CRDs, then applies the MultiClusterHub and the Provider | 120 seconds each |
| 4 | Waits until the Provider is healthy and its CRDs exist, then applies the ProviderConfig `default` | 180 and 90 seconds |
| 5 | Adds `gitops-plugin` and `pipelines-console-plugin` to the plugins of the web console | |
| 6 | Prints the state of each operator, the Provider, the ProviderConfig, the MultiClusterHub and ArgoCD | |

The script applies every manifest with `oc apply`, so it can run again after a failure.

After the install, create the AWS credentials of Crossplane; see [Credentials setup](#credentials-setup).

### Manual install

These commands do what the script does. Run them in `hub-config/`.

```bash
oc apply -f namespaces.yaml
oc apply -f cert-manager/operatorgroup.yaml -f cert-manager/subscription.yaml
oc apply -f tekton/subscription.yaml -f argocd/subscription.yaml -f acm/subscription.yaml
oc apply -f partner-labs-auth/operatorgroup.yaml -f partner-labs-auth/subscription.yaml
oc apply -f crossplane/installation/rbac.yaml -f crossplane/installation/helm-job.yaml -f crossplane/rbac/scc-binding.yaml
```

Wait until the five operators report `Succeeded`:

```bash
oc get csv -A | grep -E "cert-manager|gitops|pipelines|advanced-cluster-management|rhsso"
```

Wait for the Crossplane Job:

```bash
oc wait --for=condition=Complete job/crossplane-helm-installer -n crossplane-system --timeout=600s
```

Apply the resources that need the CRDs of the operators:

```bash
oc apply -f acm/multiclusterhub.yaml
oc apply -f crossplane/provider.yaml
oc wait --for=condition=Healthy provider.pkg.crossplane.io/provider-aws-iam --timeout=180s
oc apply -f crossplane/providerconfig.yaml
```

Add `gitops-plugin` and `pipelines-console-plugin` to `spec.plugins`:

```bash
oc edit console.operator.openshift.io cluster
```

`oc apply -k .` is not a full install. `kustomization.yaml` leaves out `crossplane/providerconfig.yaml`, and the MultiClusterHub and the Provider fail to apply until their CRDs exist.

## Credentials setup

The ProviderConfig `default` reads the Secret `aws-credentials` in `crossplane-system`, key `credentials`. The install creates the namespace, so create the Secret after it:

```bash
oc create secret generic aws-credentials \
  --from-literal=credentials="$(cat ~/.aws/credentials)" \
  -n crossplane-system
```

This identity creates the IAM users, access keys, roles and policies of every cluster. It can create IAM policies and roles, which equals account administration. Restrict access to `crossplane-system/aws-credentials`.

For scoped AWS clusters, which `fleet-cluster-scaffold` renders by default, the identity needs these IAM actions in addition to the user, policy and access-key actions that legacy clusters use:

| Purpose | IAM actions |
|---|---|
| BYO node roles | `iam:CreateRole`, `iam:GetRole`, `iam:DeleteRole`, `iam:UpdateRole`, `iam:UpdateAssumeRolePolicy`, `iam:TagRole`, `iam:UntagRole`, `iam:ListRoleTags`, `iam:PutRolePolicy`, `iam:GetRolePolicy`, `iam:DeleteRolePolicy`, `iam:ListRolePolicies`, `iam:ListAttachedRolePolicies`, `iam:ListInstanceProfilesForRole` |
| Policy updates after the install (`scope-aws-credentials`) | `iam:CreatePolicyVersion`, `iam:DeletePolicyVersion`, `iam:ListPolicyVersions`, `iam:GetPolicyVersion` |

Check the actions. Empty output means every action is allowed:

```bash
aws iam simulate-principal-policy --policy-source-arn <crossplane-identity-arn> \
  --action-names iam:CreateRole iam:GetRole iam:DeleteRole iam:UpdateRole iam:UpdateAssumeRolePolicy \
    iam:TagRole iam:UntagRole iam:ListRoleTags iam:PutRolePolicy iam:GetRolePolicy iam:DeleteRolePolicy \
    iam:ListRolePolicies iam:ListAttachedRolePolicies iam:ListInstanceProfilesForRole \
    iam:CreatePolicyVersion iam:DeletePolicyVersion iam:ListPolicyVersions iam:GetPolicyVersion \
  --query 'EvaluationResults[?EvalDecision!=`allowed`].EvalActionName'
```

| Missing actions | Effect |
|---|---|
| Role actions | `wait-for-aws-component-credentials` times out and lists the node roles with an `AccessDenied` message. |
| Policy-version actions | The operator `Policy` resources report `Synced=False` after `scope-aws-credentials`. Partner LoadBalancers and egress IPs stay denied. |

[docs/architecture.md](../docs/architecture.md#aws-credential-modes) describes the two credential modes.

## Verify

From the root of the repository:

```bash
make hub-status
```

The checks one by one:

| Component | Command | Expected |
|---|---|---|
| Operators | `oc get csv -A \| grep -E "cert-manager\|gitops\|pipelines\|advanced-cluster-management\|rhsso"` | Each line ends in `Succeeded` |
| Crossplane install | `oc get job crossplane-helm-installer -n crossplane-system` | `COMPLETIONS` shows `1/1` |
| Crossplane Provider | `oc get providers.pkg.crossplane.io` | `provider-aws-iam` with `INSTALLED` and `HEALTHY` `True` |
| ProviderConfig | `oc get providerconfig.aws.upbound.io` | `default` |
| ACM | `oc get multiclusterhub -n open-cluster-management` | `STATUS` shows `Running` |
| ArgoCD | `oc get argocds -n openshift-gitops` | `openshift-gitops` |

## Channels

Each `subscription.yaml` pins the channel of its operator. The table in [Components](#components) lists the pinned channels, and a test compares the table with the manifests.

Change a channel:

1. List the channels of the package:

   ```bash
   oc get packagemanifest <package> -n openshift-marketplace -o jsonpath='{.status.channels[*].name}'
   ```

2. Set `channel:` in `<directory>/subscription.yaml` and in the row of the Components table.

3. Apply the Subscription:

   ```bash
   oc apply -f <directory>/subscription.yaml
   ```

## ArgoCD Application

`bootstrap/` holds the ArgoCD Application `fleet-hub-config`. It syncs the directory `hub-config/` of the `main` branch to the hub, removes resources that leave the directory, and reverts manual changes to synced resources.

Apply it after the operators are installed:

```bash
oc apply -k bootstrap/
```

The Application does not manage the ProviderConfig, which `kustomization.yaml` leaves out.

## Uninstall

The uninstall removes the namespace `openshift-pipelines`, and with it the pipelines, the ConfigMap `fleet-pipeline-config` and the Secrets that [docs/hub-setup.md](../docs/hub-setup.md) creates. Deprovision every cluster first.

From the root of the repository:

```bash
make hub-uninstall
```

The target runs `hub-config/uninstall-hub-config.sh`. The script asks you to type `yes`, then does this in order:

1. Deletes the validating webhooks of ACM and ArgoCD.
2. Deletes every MultiClusterHub and MultiClusterEngine, and removes their finalizers when the deletion does not finish in 60 seconds.
3. Deletes every Crossplane Provider and ProviderConfig, and the Job `crossplane-helm-installer`.
4. Deletes the five Subscriptions, the three OperatorGroups, and every InstallPlan in `openshift-operators`, `open-cluster-management`, `cert-manager-operator` and `partner-labs-auth`.
5. Deletes the ClusterServiceVersions of the five operators.
6. Deletes the ClusterRoles, ClusterRoleBindings and ServiceAccounts `crossplane-installer` and `crossplane-privileged-scc`.
7. Removes `gitops-plugin` and `pipelines-console-plugin` from the web console.
8. Deletes the eight namespaces of `namespaces.yaml`.
9. Removes the finalizers of ACM and ArgoCD resources that remain, and of every namespace on the cluster that is in the state `Terminating`.

Two actions reach beyond this directory: step 4 deletes the InstallPlans of every operator in `openshift-operators`, and step 9 acts on every terminating namespace of the cluster.

### Manual uninstall

These commands do what the script does, without the forced removal of finalizers.

```bash
oc delete multiclusterhub --all --all-namespaces --timeout=60s
oc delete multiclusterengine --all --timeout=60s
oc delete providers.pkg.crossplane.io --all --timeout=60s
oc delete providerconfig.aws.upbound.io --all --timeout=60s
oc delete job crossplane-helm-installer -n crossplane-system
```

```bash
oc delete subscription.operators.coreos.com advanced-cluster-management -n open-cluster-management
oc delete subscription.operators.coreos.com cert-manager -n cert-manager-operator
oc delete subscription.operators.coreos.com openshift-gitops-operator openshift-pipelines-operator -n openshift-operators
oc delete subscription.operators.coreos.com rhsso-operator -n partner-labs-auth
oc delete operatorgroup open-cluster-management -n open-cluster-management
oc delete operatorgroup cert-manager-operator -n cert-manager-operator
oc delete operatorgroup partner-labs-auth -n partner-labs-auth
```

List the ClusterServiceVersions of the five operators, then delete each one by name and namespace:

```bash
oc get csv -A | grep -E "cert-manager-operator|openshift-gitops-operator|openshift-pipelines-operator|advanced-cluster-management|rhsso-operator"
```

```bash
oc delete csv <name> -n <namespace>
```

```bash
oc delete clusterrole,clusterrolebinding crossplane-installer crossplane-privileged-scc
oc delete namespace cert-manager crossplane-system multicluster-engine open-cluster-management openshift-gitops openshift-pipelines cert-manager-operator partner-labs-auth
```

Delete the custom resources before the operators. An operator that is gone cannot remove the finalizers of its resources, and their namespaces then stay in `Terminating`.

## Troubleshooting

| Symptom | Check |
|---|---|
| An operator does not reach `Succeeded` | `oc get subscription.operators.coreos.com -A`, `oc get installplans -A` and `oc get events -A --sort-by=.lastTimestamp` |
| The Crossplane Job fails | `oc logs job/crossplane-helm-installer -n crossplane-system`. The Job needs network access to `charts.crossplane.io`. |
| The ACM operator does not install | `oc describe operatorgroup -n open-cluster-management`, and `oc get csv -n openshift-operators` for a second ACM installation |
| The Provider is not healthy | `oc describe provider.pkg.crossplane.io provider-aws-iam` |
| IAM resources of a cluster stay unsynced | `oc get secret aws-credentials -n crossplane-system`; see [Credentials setup](#credentials-setup) |
