# Red Hat OpenShift AI: Component, Capability, and Operator Mapping

## Scope and assumptions

This guide consolidates the OpenShift AI component and operator mapping discussed for a `DataScienceCluster` (DSC) deployment. It distinguishes:

- **OpenShift AI 2.x** from **OpenShift AI 3.x** external/operator dependencies.
- The **mandatory platform operator** from conditional workload, accelerator, networking, scheduling, and observability operators.
- DSC components, their business/technical capabilities, and when they should be enabled.
- A practical minimal deployment for the manifest supplied in this discussion.

> **Version caution:** Red Hat OpenShift AI 3.0 introduced major architecture and component changes. It is not an in-place upgrade target from OpenShift AI 2.25 or earlier. Confirm exact availability, support status, and prerequisite details against the documentation for the exact OpenShift AI Operator channel/release you install.

---

## The supplied DataScienceCluster manifest

```yaml
kind: DataScienceCluster
apiVersion: datasciencecluster.opendatahub.io/v2
metadata:
  name: default-dsc
  labels:
    app.kubernetes.io/name: datasciencecluster
spec:
  components:
    dashboard:
      managementState: Managed
    aipipelines:
      managementState: Managed
    feastoperator:
      managementState: Managed
    kserve:
      managementState: Managed
    llamastackoperator:
      managementState: Removed
    kueue:
      managementState: Removed
    mlflowoperator:
      managementState: Managed
    sparkoperator:
      managementState: Removed
    modelregistry:
      managementState: Managed
      registriesNamespace: rhoai-model-registries
    ray:
      managementState: Managed
    workbenches:
      managementState: Managed
    trainer:
      managementState: Managed
    trainingoperator:
      managementState: Removed
    trustyai:
      managementState: Managed
```

### Management states

| State | Meaning |
|---|---|
| `Managed` | The Red Hat OpenShift AI Operator deploys and reconciles the component. |
| `Removed` | The component is not deployed; the Operator attempts to remove component resources it manages. |

---

## Core principle: which operator owns the DSC?

The **Red Hat OpenShift AI Operator** is the platform operator that owns and reconciles the `DataScienceCluster` custom resource. It deploys and manages the OpenShift AI components marked `Managed` in the DSC.

Do not interpret the list of 3.x “operators” as a list of subscriptions required for every OpenShift AI installation. Most are only needed for specific workload patterns, hardware, scheduling, networking, or observability requirements.

---

# OpenShift AI 3.x

## Baseline operators for this manifest

For the exact manifest above, the practical baseline is:

```text
Required:
- Red Hat OpenShift AI Operator
- cert-manager Operator
```

| Operator | Required? | Reason |
|---|---:|---|
| **Red Hat OpenShift AI Operator** | **Yes** | Required to create/reconcile `DataScienceCluster` and to deploy DSC components marked `Managed`. |
| **cert-manager Operator** | **Yes** | Required because `kserve: Managed` enables the KServe model-serving platform. |

This is the minimum **operator** set for a standard CPU-based OpenShift AI deployment with the DSC shown, including normal notebook/workbench workflows and ordinary KServe single-model inference.

It does **not** eliminate non-operator requirements such as object storage and an external database for some enabled capabilities.

## 3.x operator decision table

| Operator | Baseline requirement | Install when | Not required when |
|---|---:|---|---|
| **Red Hat OpenShift AI Operator** | **Required** | Always | Never, if deploying self-managed OpenShift AI through a DSC |
| **cert-manager Operator** | **Required for this manifest** | KServe model serving is enabled | KServe is not enabled and no other selected workload requires cert-manager |
| **Job Set Operator** | Conditional | Running distributed training or other enabled workflows that create/require `JobSet` resources | You are not using those distributed-training/job patterns |
| **Red Hat Build of Kueue Operator (RHBOK)** | Optional for this manifest | You enable Kueue for workload admission, queues, quotas, priorities, or fair sharing of compute/GPU capacity | `kueue: Removed` and you do not need centralized queue/admission control |
| **NVIDIA GPU Operator** | Conditional | NVIDIA GPU-backed workbenches, training, or model serving | CPU-only platform or a different supported accelerator stack |
| **Node Feature Discovery** | Conditional | Required by your selected GPU/accelerator installation design for hardware discovery and labeling | Your hardware/operator guidance does not require it |
| **SR-IOV Operator** | Conditional | Your specialized accelerator/network deployment requires SR-IOV networking | Standard networking is sufficient |
| **Leader Worker Set Operator** | Conditional | Advanced multi-node/distributed inference using llm-d | Standard KServe single-model inference |
| **Red Hat Connectivity Link Operator** | Conditional | Advanced llm-d distributed-inference architecture requires the connectivity layer | Standard KServe inference |
| **OpenShift Custom Metrics Autoscaler Operator** | Optional | You explicitly require custom-metric autoscaling for supported workloads | Standard autoscaling or no special autoscaling is sufficient |
| **OpenTelemetry Operator** | Optional | You need OpenTelemetry instrumentation/collection | You do not use this telemetry integration |
| **Tempo Operator** | Optional | You need distributed-trace storage and analysis | You do not need distributed tracing |
| **Cluster Observability Operator** | Optional | You use the associated observability integration/features | Standard platform monitoring is sufficient |
| **IBM Spyre Operator** | Conditional | OpenShift AI runs on IBM Spyre accelerator hardware | You are not using IBM Spyre |

### Important distinction: normal versus advanced KServe

**Normal KServe serving** requires OpenShift AI plus cert-manager. It is used for ordinary single-model inference endpoints.

**Advanced distributed LLM inference (llm-d)** is a separate deployment mode. It may add requirements such as the Leader Worker Set Operator and Red Hat Connectivity Link Operator, along with accelerator and networking prerequisites. Do not install those operators merely because `kserve: Managed` is present.

## 3.x component-to-capability mapping

| DSC component | State in supplied manifest | Capability | Needed for “essential” OpenShift AI? | Operator relationship and major non-operator dependencies |
|---|---:|---|---|---|
| `dashboard` | Managed | OpenShift AI browser UI: project access, workload configuration, and discovery of enabled services | Usually yes for a supported self-service experience | Managed by the OpenShift AI Operator; no separate component operator subscription |
| `workbenches` | Managed | Interactive development environments, typically Jupyter-based | Yes for interactive data science/development | Managed by OpenShift AI Operator; GPU use can require the NVIDIA GPU Operator and related hardware configuration |
| `aipipelines` | Managed | Repeatable, orchestrated ML/data-science workflows | Optional; enable for workflow orchestration | Managed by OpenShift AI Operator; requires/recommends S3-compatible object storage for artifacts, outputs, and logs |
| `kserve` | Managed | Model serving through scalable inference endpoints | Required only if deploying models as services/endpoints | Managed by OpenShift AI Operator; **cert-manager is required**; requires usable S3-compatible object storage for model artifacts |
| `modelregistry` | Managed | Central model/version metadata, provenance, lifecycle, and promotion | Recommended for governed MLOps; not required for notebooks or basic serving | Managed by OpenShift AI Operator; requires external MySQL (5.x+, 8.x recommended) and S3-compatible object storage. `registriesNamespace` identifies the namespace for registry resources |
| `mlflowoperator` | Managed | MLflow experiment tracking for runs, parameters, metrics, and artifacts | Optional; enable when teams standardize on MLflow | DSC-managed in relevant 3.x releases/channels; verify exact release support; requires appropriate artifact/backend-store design |
| `feastoperator` | Managed | Feature-store capability based on Feast: reusable online/offline ML features | Optional; only for a formal feature-store architecture | DSC-managed integration; requires a deliberate backing-store, networking, and operations design |
| `ray` | Managed | Distributed Python workloads with Ray, including distributed compute, tuning, and Ray-based patterns | Optional; only for Ray workloads | Managed by OpenShift AI Operator. Add Kueue separately for cluster-wide admission/queue/quota controls if needed |
| `trainer` | Managed | Current distributed training capability for supported training workloads | Optional; only for distributed training | Managed by OpenShift AI Operator. Specific workloads may require Job Set Operator; Kueue is recommended when shared capacity must be scheduled/governed |
| `trustyai` | Managed | Responsible-AI features such as monitoring, evaluation, fairness/bias-related capabilities, and explainability-related services | Optional; required only for those governance/monitoring goals | Managed by OpenShift AI Operator; underlying service is commonly referred to as TrustyAI Service Operator |
| `llamastackoperator` | Removed | Llama Stack / GenAI and RAG-related workloads | Not essential | If enabled, expect extra dependencies such as Service Mesh 3.x, cert-manager, GPU nodes, Node Feature Discovery, NVIDIA GPU Operator, and object storage; exact requirements vary by release |
| `kueue` | Removed | Queueing, workload admission, quota, priority, and fair sharing | Not essential | Enable only with the Red Hat Build of Kueue Operator (RHBOK). Particularly useful for shared GPU and distributed-workload clusters |
| `sparkoperator` | Removed | Kubernetes-native Apache Spark processing / ML workloads | Not essential | Enable only for Spark ETL, feature engineering, or Spark ML workloads |
| `trainingoperator` | Removed | Legacy Kubeflow Training Operator path | Not recommended for OpenShift AI 3.x baseline | Keep removed unless a specifically supported legacy workload requires it; prefer `trainer` where applicable |

## Capability profiles for OpenShift AI 3.x

| Goal | Components to enable | Operators beyond OpenShift AI Operator |
|---|---|---|
| Interactive development only | `dashboard`, `workbenches` | None by default; GPU Operator only for NVIDIA GPU workloads |
| Repeatable data/ML workflows | Add `aipipelines` | None by default |
| Standard real-time model serving | Add `kserve` | **cert-manager Operator** |
| Governed MLOps / model lifecycle | Add `modelregistry` | No additional operator by default; external MySQL and object storage required |
| MLflow experiments | Add `mlflowoperator` | No additional operator by default; plan tracking/artifact stores |
| Feature store | Add `feastoperator` | No additional operator by default; plan feature-store backing services |
| Ray distributed workloads | Add `ray` | Kueue optional for quotas/admission; GPU Operator if using NVIDIA GPUs |
| Distributed training | Add `trainer` | Job Set Operator may be required by the chosen workload; add Kueue for queue/admission/quotas; GPU Operator for NVIDIA GPUs |
| Responsible AI and model monitoring | Add `trustyai` | No separate operator in the ordinary DSC-managed setup |
| Advanced multi-node LLM inference | `kserve` plus relevant advanced inference configuration | cert-manager, Leader Worker Set Operator, Connectivity Link Operator, GPU/hardware dependencies as applicable |
| Llama Stack / RAG | Enable `llamastackoperator` | Additional service-mesh, certificate, GPU/hardware, and storage prerequisites; validate exact version documentation |

## Recommended component profiles

### Lean development platform

```yaml
components:
  dashboard:
    managementState: Managed
  workbenches:
    managementState: Managed
```

Use when teams need interactive environments but do not need platform-managed pipelines, serving, formal model lifecycle, distributed compute, or monitoring.

### Conventional production MLOps

```yaml
components:
  dashboard:
    managementState: Managed
  workbenches:
    managementState: Managed
  aipipelines:
    managementState: Managed
  kserve:
    managementState: Managed
  modelregistry:
    managementState: Managed
```

This is a lean, production-oriented base for development, repeatable pipelines, model lifecycle, and inference endpoints. Install cert-manager, provide S3-compatible object storage, and deploy external MySQL for Model Registry.

### Add only for explicit needs

- Add `mlflowoperator` for MLflow-based experiment tracking.
- Add `trustyai` for evaluation, model monitoring, explainability, and responsible-AI governance goals.
- Add `ray` for Ray-specific distributed workloads.
- Add `trainer` for supported distributed training.
- Add `kueue` with RHBOK when several teams/workloads share constrained CPU/GPU capacity and require queues, quotas, priority, or fair sharing.
- Add `feastoperator` only when a feature store is an architectural requirement.
- Add `llamastackoperator` only for its specific GenAI/RAG/Llama Stack use cases.

---

# OpenShift AI 2.x

## 2.x operators called out as required dependencies

The dependency list shown for OpenShift AI 2.x identifies these operators:

```text
- Authorino Operator
- Service Mesh Operator
- Serverless Operator
```

These operators belong to the 2.x architecture/dependency model and should **not** be carried forward automatically as a baseline assumption for OpenShift AI 3.x.

| OpenShift AI version | Operators listed as required dependencies | Practical meaning |
|---|---|---|
| **2.x** | Authorino Operator, Service Mesh Operator, Serverless Operator | Install according to supported 2.x architecture and feature requirements. They are not the universal 3.x baseline. |
| **3.x** | See 3.x decision table above | The universal baseline is OpenShift AI Operator; cert-manager is required when KServe is enabled. Other operators are feature-specific. |

### 2.x and 3.x migration warning

OpenShift AI 3.0 contains significant component and architectural changes. Treat the 3.x installation as a separate deployment/migration planning exercise rather than assuming a direct upgrade from OpenShift AI 2.25 or earlier.

---

# Non-operator dependencies

Operators are only part of the deployment design. The following platform services may be required even when no additional OperatorHub subscription is needed.

| Capability/component | Non-operator dependency | Why it matters |
|---|---|---|
| `aipipelines` | S3-compatible object storage | Pipeline artifacts, intermediate outputs, logs, and results |
| `kserve` | S3-compatible object storage | Storage and retrieval of model artifacts |
| `modelregistry` | External MySQL database, plus S3-compatible object storage | Model Registry metadata backend and artifact-related use cases |
| `mlflowoperator` | Backend and artifact-store design | MLflow requires appropriate storage for run metadata and artifacts |
| `feastoperator` | Feature-store backing services | Feast requires online/offline store choices and operational configuration |
| GPU workloads | GPU nodes, drivers, runtime, capacity planning | Required to schedule and run accelerator-backed workbenches, training, or inference |
| Distributed workloads | Capacity, scheduling design, shared storage/networking as relevant | Prevents admission conflicts and performance/resource issues |

---

# Decision procedure

Use this sequence to choose operators deliberately.

1. **Install the Red Hat OpenShift AI Operator.** It is required to use the DSC.
2. **Determine whether KServe is enabled.** If yes, install cert-manager.
3. **Determine hardware needs.** Add NVIDIA GPU Operator and any required vendor/hardware discovery dependencies only if GPU/accelerator workloads are planned.
4. **Determine whether you run distributed training.** Add Job Set Operator only when the selected trainer workload requires it.
5. **Determine whether shared-resource governance is required.** Add RHBOK and enable `kueue` when queueing, admission, quotas, priorities, or fair sharing are needed.
6. **Determine whether advanced distributed inference is in scope.** Add Leader Worker Set and Connectivity Link only for llm-d-style advanced inference, not standard KServe.
7. **Add telemetry and specialized networking operators only for explicit architecture requirements.**

---

# Final checklist for the supplied manifest

## Required now

- [ ] Red Hat OpenShift AI Operator
- [ ] cert-manager Operator, because `kserve: Managed`
- [ ] S3-compatible object storage, because KServe and AI Pipelines are enabled
- [ ] External MySQL 5.x+ (8.x recommended) for `modelregistry`

## Conditional based on actual workload use

- [ ] NVIDIA GPU Operator and related hardware configuration for NVIDIA GPU workloads
- [ ] Job Set Operator for trainer workflows that require `JobSet`
- [ ] Red Hat Build of Kueue Operator if enabling Kueue for quotas/admission/fair sharing
- [ ] Leader Worker Set Operator and Red Hat Connectivity Link Operator only for advanced llm-d distributed inference
- [ ] Feature-store backing services if using Feast
- [ ] MLflow backend/artifact storage if using MLflow
- [ ] Telemetry/tracing operators only if those integrations are intentionally deployed

## Not required by the supplied manifest

- [ ] Kueue Operator, because `kueue: Removed`
- [ ] Legacy Kubeflow Training Operator, because `trainingoperator: Removed`
- [ ] Spark Operator, because `sparkoperator: Removed`
- [ ] Llama Stack-specific dependencies, because `llamastackoperator: Removed`
- [ ] Leader Worker Set / Connectivity Link, unless adopting advanced distributed LLM inference
- [ ] SR-IOV Operator, unless required by a specialized network/accelerator design
- [ ] IBM Spyre Operator, unless running IBM Spyre hardware

---

# Sources consulted

- Red Hat OpenShift AI Self-Managed installation/deployment documentation for 3.x, including dependency and component guidance.
- Red Hat OpenShift AI 3.x release notes, including component/dependency changes such as Kueue and training-operator lifecycle changes.
- The supplied operator-dependency screenshot, which lists 2.x and 3.x operator categories.

For implementation, use the documentation matching your exact OpenShift AI release/channel, OpenShift Container Platform version, accelerator vendor, and selected feature set. This is especially important for Technology Preview features and components whose operational status changed across OpenShift AI 3.x releases.
