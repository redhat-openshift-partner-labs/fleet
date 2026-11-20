# Image Pull Secret Setup

This guide describes how to create, verify and rotate the pull secret of the pipeline image.

It is step 4 of the [hub setup](hub-setup.md). Every task step of every pipeline runs in the image `quay.io/rhopl/fleet-pipeline`, and quay.io requires authentication to pull it.

## How it works

- `oc apply -k tekton/` creates the Secret `fleet-pipeline-pull-secret` in `openshift-pipelines` from [tekton/rbac/quay-pull-secret.yaml](../tekton/rbac/quay-pull-secret.yaml). The manifest holds a placeholder, so the Secret in git cannot pull the image.
- The ServiceAccount `fleet-pipeline` lists the Secret in `imagePullSecrets`. Every pipeline run uses this ServiceAccount.
- The administrator replaces the placeholder on the hub with the credentials of a quay.io robot account.

Every `oc apply -k tekton/` writes the placeholder again. Repeat step 2 after it.

These files name the Secret. Change all of them to rename it.

| File | Use |
|---|---|
| `tekton/rbac/quay-pull-secret.yaml` | The Secret |
| `tekton/rbac/serviceaccount.yaml` | `imagePullSecrets` of `fleet-pipeline` |
| `tekton/triggers/triggertemplate-pre-provision.yaml` | Pod template of the `pre-provision` run the EventListener starts |
| `fleet/tasks/trigger_provision.py`, `fleet/tasks/trigger_post_provision.py`, `fleet/tasks/run_post_provision.py` | Pod template of the runs these tasks start |
| `tekton/pod-template.yaml` | A pod template file. No manifest references it. |

## Setup

### 1. Create a quay.io robot account

1. Log in to [quay.io](https://quay.io) and open the organization `rhopl`.
2. Open **Robot Accounts** and create a robot account, for example `rhopl+fleet_pipeline_pull`.
3. Give the robot account the permission **Read** on the repository `rhopl/fleet-pipeline`.
4. Copy the user name and the token of the robot account.

### 2. Store the credentials on the hub

```bash
oc create secret docker-registry fleet-pipeline-pull-secret \
  --docker-server=quay.io \
  --docker-username='<robot-account>' \
  --docker-password='<token>' \
  -n openshift-pipelines \
  --dry-run=client -o yaml | oc apply -f -
```

### 3. Verify

Check that the ServiceAccount lists the Secret:

```bash
oc get serviceaccount fleet-pipeline -n openshift-pipelines -o jsonpath='{.imagePullSecrets[*].name}'
```

The output is `fleet-pipeline-pull-secret`.

Start a pod that pulls the image as the ServiceAccount:

```bash
oc run test-pull --image=quay.io/rhopl/fleet-pipeline:latest \
  --restart=Never \
  --overrides='{"spec":{"serviceAccountName":"fleet-pipeline"}}' \
  -n openshift-pipelines \
  --command -- echo "pull succeeded"
```

```bash
oc get pod test-pull -n openshift-pipelines
```

`STATUS` shows `Completed`. `ErrImagePull` or `ImagePullBackOff` means the credentials are wrong or the robot account cannot read the repository.

Delete the pod:

```bash
oc delete pod test-pull -n openshift-pipelines
```

## Rotate the token

1. Generate a new token for the robot account in quay.io.
2. Run the command of step 2 with the new token.

Pods that already run are not affected. Pods that start after the change use the new token.
