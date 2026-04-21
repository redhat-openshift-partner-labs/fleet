# Image Pull Secret Setup

The fleet Tekton pipelines use a custom container image (`quay.io/rhopl/fleet-pipeline`) for all task steps. This image is hosted in a private quay.io repository and requires authentication to pull.

## How it works

- A `kubernetes.io/dockerconfigjson` Secret named `fleet-pipeline-pull-secret` is deployed to the `openshift-pipelines` namespace via kustomize (`tekton/rbac/quay-pull-secret.yaml`).
- The `fleet-pipeline` ServiceAccount references this secret in its `imagePullSecrets` field.
- When Tekton creates TaskRun pods, the kubelet uses these credentials to authenticate against quay.io.

The manifest in git contains a placeholder value. Real credentials must be populated on the hub cluster out-of-band.

## Setup procedure

### 1. Create a quay.io robot account

1. Log in to [quay.io](https://quay.io) and navigate to the `rhopl` organization.
2. Go to **Robot Accounts** and create a robot account (e.g., `rhopl+fleet_pipeline_pull`).
3. Grant the robot account **Read** permission on the `rhopl/fleet-pipeline` repository.
4. Copy the robot account credentials (username and token).

### 2. Populate the secret on the hub cluster

Generate the base64-encoded auth string and apply the secret:

```bash
# Build the auth string (username:token, base64-encoded)
AUTH=$(echo -n 'rhopl+fleet_pipeline_pull:TOKEN_HERE' | base64)

# Create the secret directly (overrides the placeholder from git)
oc create secret docker-registry fleet-pipeline-pull-secret \
  --docker-server=quay.io \
  --docker-username='rhopl+fleet_pipeline_pull' \
  --docker-password='TOKEN_HERE' \
  -n openshift-pipelines \
  --dry-run=client -o yaml | oc apply -f -
```

### 3. Verify

Confirm the ServiceAccount has the pull secret linked:

```bash
oc get serviceaccount fleet-pipeline -n openshift-pipelines -o yaml | grep -A2 imagePullSecrets
```

Test that a pod can pull the image:

```bash
oc run test-pull --image=quay.io/rhopl/fleet-pipeline:latest \
  --restart=Never \
  --serviceaccount=fleet-pipeline \
  -n openshift-pipelines \
  --command -- echo "pull succeeded"

# Check status
oc get pod test-pull -n openshift-pipelines

# Cleanup
oc delete pod test-pull -n openshift-pipelines
```

## Credential rotation

When rotating the quay.io robot account token:

1. Generate a new token in the quay.io UI.
2. Re-run the `oc create secret docker-registry` command from step 2 with the new token.
3. Existing running pipelines are unaffected; new TaskRun pods will use the updated credentials.

## Sealed Secrets alternative

If the hub cluster runs Sealed Secrets, you can encrypt the real credentials and commit the SealedSecret to git instead of using the placeholder:

```bash
# Create the real secret, pipe through kubeseal
oc create secret docker-registry fleet-pipeline-pull-secret \
  --docker-server=quay.io \
  --docker-username='rhopl+fleet_pipeline_pull' \
  --docker-password='TOKEN_HERE' \
  -n openshift-pipelines \
  --dry-run=client -o yaml | \
  kubeseal --format yaml > tekton/rbac/quay-pull-secret-sealed.yaml
```

Then replace `quay-pull-secret.yaml` with the sealed version in `tekton/rbac/kustomization.yaml`.
