# Hub Setup

This guide describes the one-time setup of the hub cluster, in order: the operators, the pipelines, their configuration and Secrets, and the connection to fleet-clusters.

When the setup is complete, an operator can provision a cluster with the [user guide](user-guide.md). Run every command from the root of this repository unless a step says otherwise.

## Requirements

| Requirement | Detail |
|---|---|
| Hub cluster | OpenShift 4.12 or later, with the catalog `redhat-operators` and network access to operator images, `charts.crossplane.io` and `xpkg.upbound.io` |
| Size | At least 16 vCPU, 64 GB RAM and 200 GB storage |
| Storage class | `gp3-csi`. Every pipeline run requests its workspace from this class. |
| Tools | `oc` logged in as a cluster administrator, `jq`, and `aws` for the IAM check |
| AWS identity | One identity for Crossplane with the IAM actions listed in [hub-config/README.md](../hub-config/README.md#credentials-setup) |
| GitHub | Administrator access to fleet-clusters, to add a webhook, a deploy key and a GitHub App |
| quay.io | A robot account that can read `quay.io/rhopl/fleet-pipeline` |

## Steps

### 1. Install the operators

```bash
make hub-install
```

The command installs ACM, OpenShift GitOps, OpenShift Pipelines, cert-manager, RH-SSO and Crossplane. [hub-config/README.md](../hub-config/README.md#install) describes each step and how to check the result.

### 2. Create the Crossplane AWS credentials

```bash
oc create secret generic aws-credentials \
  --from-literal=credentials="$(cat ~/.aws/credentials)" \
  -n crossplane-system
```

[hub-config/README.md](../hub-config/README.md#credentials-setup) lists the IAM actions the identity needs and the command that checks them.

### 3. Install the pipelines

```bash
oc apply -k tekton/
```

The command creates these resources in `openshift-pipelines`:

- ConfigMap `fleet-pipeline-config`
- ServiceAccount `fleet-pipeline` with its ClusterRole and ClusterRoleBinding
- Secret `fleet-pipeline-pull-secret` with a placeholder value
- The tasks, the five pipelines, and the EventListener `fleet-cluster-lifecycle` with its bindings and templates

Check:

```bash
oc get pipelines -n openshift-pipelines
```

The output lists `pre-provision`, `provision`, `post-provision`, `deprovision` and `test-vcluster`.

The pipelines also use the Task `git-clone`, which OpenShift Pipelines provides:

```bash
oc get task git-clone -n openshift-pipelines
```

Every later `oc apply -k tekton/` writes the values in git again: the placeholder of the pull secret and the defaults of the ConfigMap. Repeat steps 4 and 6 after it.

### 4. Create the pull secret of the pipeline image

Follow [image-pull-secret-setup.md](image-pull-secret-setup.md). It replaces the placeholder of `fleet-pipeline-pull-secret` with the credentials of the quay.io robot account.

### 5. Set up Keycloak

`make hub-install` installs the RH-SSO operator in `partner-labs-auth`. This repository holds no manifest for the Keycloak instance and the realm.

1. Create a Keycloak instance and a realm for the clusters with the operator.
2. Store an admin user of the instance:

   ```bash
   oc create secret generic keycloak-admin \
     --from-literal=username=<admin-user> \
     --from-literal=password=<admin-password> \
     -n openshift-pipelines
   ```

`register-keycloak-client` logs in with this user and creates one OIDC client per cluster in the realm.

### 6. Set the pipeline configuration

Every pipeline reads the ConfigMap `fleet-pipeline-config` in its first task. Set the keys of the table to the values of your hub:

```bash
oc edit configmap fleet-pipeline-config -n openshift-pipelines
```

| Key | Default | Set to |
|---|---|---|
| `keycloak-url` | `https://keycloak.example.com` | Base URL of the Keycloak instance |
| `keycloak-realm` | `openshift` | Realm that holds the OIDC clients of the clusters |
| `keycloak-issuer-url` | `https://keycloak.example.com/realms/openshift` | `<keycloak-url>/realms/<keycloak-realm>` |
| `auth-realm` | `master` | Realm in which the admin user of step 5 logs in |
| `base-domain` | `example.com` | Base DNS domain of the clusters |
| `acme-email` | `admin@example.com` | Email address of the Let's Encrypt account |
| `cluster-admins` | Empty | Users of the group `cluster-admins` on every spoke, separated by commas |
| `github-app-id` | Empty | App ID of the GitHub App; see [fleet-clusters-setup.md](fleet-clusters-setup.md#github-app) |
| `github-app-installation-id` | Empty | Installation ID of the GitHub App |
| `privatebin-url` | `https://pastes.openshiftpartnerlabs.com` | URL of the PrivateBin service that holds the access pastes |

[tekton/configmap-defaults.yaml](../tekton/configmap-defaults.yaml) holds every key. The other keys work with their defaults. [parameter-threading.md](parameter-threading.md) describes how a value reaches a task.

### 7. Give git-clone access to the repositories

The pipelines clone fleet-clusters and fleet over SSH.

1. Create an SSH key pair without a passphrase and add the public key as a read-only deploy key to both repositories.
2. Store the private key and the host key of GitHub, and link the Secret to the ServiceAccount of the pipelines:

   ```bash
   ssh-keyscan github.com > known_hosts
   oc create secret generic fleet-git-ssh \
     --type=kubernetes.io/ssh-auth \
     --from-file=ssh-privatekey=<private-key-file> \
     --from-file=known_hosts=known_hosts \
     -n openshift-pipelines
   oc annotate secret fleet-git-ssh tekton.dev/git-0=github.com -n openshift-pipelines
   oc secrets link fleet-pipeline fleet-git-ssh -n openshift-pipelines
   ```

Tekton gives the key to the `git-clone` step of every run that uses `fleet-pipeline`.

### 8. Expose the EventListener

The webhook of fleet-clusters needs a URL that reaches the EventListener:

```bash
oc create route edge fleet-cluster-lifecycle \
  --service=el-fleet-cluster-lifecycle \
  --port=http-listener \
  -n openshift-pipelines
```

Print the host name for the webhook:

```bash
oc get route fleet-cluster-lifecycle -n openshift-pipelines -o jsonpath='{.spec.host}'
```

### 9. Connect fleet-clusters

Follow [fleet-clusters-setup.md](fleet-clusters-setup.md). It creates the webhook with the Secret `fleet-webhook-secret`, and the GitHub App with the Secret `fleet-github-app-key`.

### 10. Check the account of the cluster job

`create-cluster-cronjob` creates one CronJob per cluster in the namespace `default`, and the CronJob runs as the ServiceAccount `ecoeng`. The task fails when the ServiceAccount does not exist. This repository does not create it.

```bash
oc get serviceaccount ecoeng -n default
```

## Secrets and accounts

| Name | Namespace | Keys | Read by | Created in |
|---|---|---|---|---|
| `aws-credentials` | `crossplane-system` | `credentials` | Crossplane ProviderConfig `default` | Step 2 |
| `fleet-pipeline-pull-secret` | `openshift-pipelines` | `.dockerconfigjson` | Every pod of a pipeline run | Step 4 |
| `keycloak-admin` | `openshift-pipelines` | `username`, `password` | `register-keycloak-client` | Step 5 |
| `fleet-git-ssh` | `openshift-pipelines` | `ssh-privatekey`, `known_hosts` | `git-clone` | Step 7 |
| `fleet-webhook-secret` | `openshift-pipelines` | `WebHookSecretKey` | EventListener `fleet-cluster-lifecycle` | Step 9 |
| `fleet-github-app-key` | `openshift-pipelines` | `private-key` | `create-deployment-status` | Step 9 |
| `fleet-iam-read-only` | `openshift-pipelines` | `FLEET_IAM_AWS_ACCOUNT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | `cleanup-hub-artifacts`. Optional; see the [user guide](user-guide.md#iam-resources-that-remain). | When needed |
| ServiceAccount `ecoeng` | `default` | None | The CronJob of each cluster | Outside this repository |

The names `keycloak-admin` and `fleet-github-app-key` are the defaults of `keycloak-admin-secret` and `github-app-key-secret` in the ConfigMap. The pipelines create every other Secret themselves, per cluster.

## Verify

| Part | Command | Expected |
|---|---|---|
| Operators | `make hub-status` | Every operator ends in `Succeeded` |
| Pipelines | `oc get pipelines -n openshift-pipelines` | The five pipelines |
| EventListener | `oc get eventlistener fleet-cluster-lifecycle -n openshift-pipelines` | `AVAILABLE` shows `True` |
| Route | `oc get route fleet-cluster-lifecycle -n openshift-pipelines` | A host name |
| Pull secret | The test pod of [image-pull-secret-setup.md](image-pull-secret-setup.md#3-verify) | The pod completes |
| Secrets | `oc get secret keycloak-admin fleet-git-ssh fleet-webhook-secret fleet-github-app-key -n openshift-pipelines` | Four Secrets |
| Crossplane | `oc get providers.pkg.crossplane.io` | `provider-aws-iam` with `HEALTHY` `True` |
| Cluster job account | `oc get serviceaccount ecoeng -n default` | The ServiceAccount |

The first cluster is the end-to-end check: provision a `base` cluster with the [user guide](user-guide.md#provision-a-cluster), then deprovision it.
