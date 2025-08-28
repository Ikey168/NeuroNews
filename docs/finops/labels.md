# NeuroNews FinOps Labeling Governance

A comprehensive cost allocation and governance system using Kubernetes labels enforced by Kyverno policies.

## Overview

This system implements standardized cost allocation labels across all Kubernetes workloads to enable:

- **Accurate cost attribution** by team, pipeline, and business unit
- **Resource governance** through automated policy enforcement
- **Financial visibility** with detailed cost breakdown and reporting
- **Compliance enforcement** ensuring all workloads follow labeling standards

## Required Labels Schema

All workloads must include these six labels for cost allocation:

### Core Labels

| Label | Type | Description | Examples |
|-------|------|-------------|----------|
| `app` | string | Application or service name | `neuronews-api`, `kafka-connect`, `prometheus` |
| `component` | string | Component type within application | `backend`, `frontend`, `database`, `cache` |
| `pipeline` | enum | Data pipeline or business function | `ingest`, `transform`, `api`, `rag`, `monitoring` |
| `team` | string | Owning team responsible for workload | `neuronews`, `data-engineering`, `platform` |
| `env` | enum | Environment designation | `dev`, `staging`, `prod`, `test` |
| `cost_center` | string | Business cost center for chargeback | `product`, `data-platform`, `infrastructure` |

### Pipeline Values

| Value | Description | Use Cases |
|-------|-------------|-----------|
| `ingest` | Data ingestion and collection | Kafka, scrapers, connectors |
| `transform` | Data transformation and processing | Spark jobs, ETL pipelines |
| `dbt` | DBT models and transformations | DBT runner, data models |
| `api` | API services and endpoints | REST APIs, GraphQL services |
| `rag` | RAG and ML inference | LLM inference, embeddings |
| `monitoring` | Observability and monitoring | Prometheus, Grafana, exporters |
| `infra` | Infrastructure and platform services | Operators, controllers, utilities |

### Environment Values

| Value | Description | SLA Level |
|-------|-------------|-----------|
| `prod` | Production environment | High availability, 24/7 monitoring |
| `staging` | Pre-production testing | Business hours support |
| `dev` | Development environment | Best effort support |
| `test` | Automated testing | Ephemeral, no SLA |

## Installation

### Prerequisites

- Kubernetes cluster (1.20+)
- `kubectl` configured for cluster access
- `kustomize` for overlay management
- Cluster admin permissions

### Quick Install

```bash
# Install FinOps labeling governance
cd k8s/finops
./install.sh

# Enable enforcement after validation period (2 weeks recommended)
./install.sh enforce
```

### Step-by-Step Installation

1. **Install Kyverno**:
   ```bash
   kubectl apply -f https://github.com/kyverno/kyverno/releases/latest/download/install.yaml
   ```

2. **Apply labeling schema**:
   ```bash
   kubectl apply -f labeling-schema.yaml
   ```

3. **Install policies in audit mode**:
   ```bash
   kubectl apply -f kyverno-policies.yaml
   ```

4. **Patch existing workloads**:
   ```bash
   kustomize build . | kubectl apply -f -
   ```

5. **Validate installation**:
   ```bash
   ./install.sh validate
   ```

## Usage Examples

### Adding Labels to New Workloads

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
  namespace: neuronews
  labels:
    # Required FinOps labels
    app: my-service
    component: backend
    pipeline: api
    team: neuronews
    env: prod
    cost_center: product
    
    # Optional labels
    version: v1.2.3
    tier: high
spec:
  template:
    metadata:
      labels:
        # Must include same labels on pods
        app: my-service
        component: backend
        pipeline: api
        team: neuronews
        env: prod
        cost_center: product
```

### Validating Label Compliance

```bash
# Check policy violations
kubectl get events --field-selector reason=PolicyViolation

# Generate compliance report
./install.sh report

# View policy status
kubectl get clusterpolicy
```

### Cost Allocation Queries

```bash
# View costs by team
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.labels.team}{"\t"}{.metadata.name}{"\n"}{end}' | sort

# View costs by pipeline
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.labels.pipeline}{"\t"}{.metadata.name}{"\n"}{end}' | sort

# View costs by cost center
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.labels.cost_center}{"\t"}{.metadata.name}{"\n"}{end}' | sort
```

## Governance Policies

### Policy: require-finops-labels

Ensures all workloads have the six required FinOps labels.

**Enforced on**: Pods, Deployments, StatefulSets, Jobs, CronJobs  
**Excluded**: System namespaces (kube-system, kyverno, etc.)  
**Action**: Block resource creation without required labels

### Policy: validate-finops-label-values

Validates that enum labels contain only allowed values.

**Validated labels**:
- `pipeline`: Must be one of ingest|transform|dbt|api|rag|monitoring|infra
- `env`: Must be one of dev|staging|prod|test

### Policy: generate-missing-finops-labels

Automatically adds default labels based on namespace patterns.

**Default mappings**:
- `monitoring` namespace → `pipeline: monitoring`, `team: platform`
- `neuronews` namespace → `team: neuronews`, `cost_center: product`

## Cost Allocation Examples

### Example: Data Engineering Team Allocation

```yaml
# Kafka Connect (Data Ingestion)
labels:
  app: kafka-connect
  component: stream-processor
  pipeline: ingest
  team: data-engineering
  env: prod
  cost_center: data-platform

# Spark ETL Job (Data Transformation)
labels:
  app: spark-etl
  component: etl-job
  pipeline: transform
  team: data-engineering
  env: prod
  cost_center: data-platform
```

### Example: Product Team Allocation

```yaml
# API Backend
labels:
  app: neuronews-api
  component: backend
  pipeline: api
  team: neuronews
  env: prod
  cost_center: product

# ML Inference Service
labels:
  app: rag-service
  component: ml-inference
  pipeline: rag
  team: ml-engineering
  env: prod
  cost_center: product
```

### Example: Platform Team Allocation

```yaml
# Monitoring Infrastructure
labels:
  app: prometheus
  component: metrics-collector
  pipeline: monitoring
  team: platform
  env: prod
  cost_center: infrastructure

# Cost Management
labels:
  app: opencost
  component: cost-analyzer
  pipeline: monitoring
  team: platform
  env: prod
  cost_center: infrastructure
```

## OpenCost Integration

Labels automatically feed into OpenCost for detailed cost analysis:

```bash
# View cost by team
curl "http://opencost:9003/allocation?window=7d&aggregate=label:team"

# View cost by pipeline
curl "http://opencost:9003/allocation?window=7d&aggregate=label:pipeline"

# View cost by cost center
curl "http://opencost:9003/allocation?window=7d&aggregate=label:cost_center"

# Combined allocation view
curl "http://opencost:9003/allocation?window=7d&aggregate=label:team,label:pipeline,label:env"
```

## Troubleshooting

### Common Issues

**Policy Violation: Missing Labels**

```bash
# Error message
"FinOps cost allocation labels are required. Missing labels: app, component, pipeline, team, env, cost_center"

# Solution
kubectl patch deployment my-deployment -p '{"metadata":{"labels":{"app":"my-app","component":"backend","pipeline":"api","team":"my-team","env":"prod","cost_center":"product"}}}'
```

**Policy Violation: Invalid Pipeline Value**

```bash
# Error message  
"Invalid pipeline label value. Allowed values: ingest, transform, dbt, api, rag, monitoring, infra"

# Solution
kubectl patch deployment my-deployment -p '{"metadata":{"labels":{"pipeline":"api"}}}'
```

**Deployment Blocked by Policy**

```bash
# Check policy events
kubectl get events --field-selector reason=PolicyViolation

# View policy details
kubectl describe clusterpolicy require-finops-labels

# Temporarily disable enforcement (emergency only)
kubectl patch clusterpolicy require-finops-labels --type='merge' -p='{"spec":{"validationFailureAction":"audit"}}'
```

### Debugging Commands

```bash
# View all policies
kubectl get clusterpolicy

# Check policy status
kubectl describe clusterpolicy require-finops-labels

# View recent policy events
kubectl get events --sort-by='.lastTimestamp' | grep -i policy

# Generate compliance report
./install.sh report

# Test policy with dry-run
kubectl apply --dry-run=server -f test-deployment.yaml
```

### Emergency Procedures

**Disable Enforcement Temporarily**:
```bash
# Switch to audit mode (allows resources but logs violations)
kubectl patch clusterpolicy require-finops-labels --type='merge' -p='{"spec":{"validationFailureAction":"audit"}}'
kubectl patch clusterpolicy validate-finops-label-values --type='merge' -p='{"spec":{"validationFailureAction":"audit"}}'
```

**Re-enable Enforcement**:
```bash
./install.sh enforce
```

## Migration Guide

### Phase 1: Audit Mode (2 weeks)

1. Install policies in audit mode
2. Monitor policy violations
3. Generate compliance reports
4. Plan labeling strategy for existing workloads

### Phase 2: Apply Labels (2 weeks)

1. Apply Kustomize overlays to patch existing resources
2. Update deployment templates with required labels
3. Validate label coverage across all namespaces
4. Train teams on labeling requirements

### Phase 3: Enforcement (1 week)

1. Switch policies to enforce mode
2. Monitor for blocked deployments
3. Handle exemption requests through governance process
4. Establish ongoing compliance monitoring

## Maintenance

### Regular Tasks

**Weekly**:
- Generate compliance reports
- Review policy violations
- Update cost allocation dashboards

**Monthly**:
- Review cost center allocations
- Update team mappings
- Audit exemption requests

**Quarterly**:
- Review labeling schema effectiveness
- Update cost allocation strategy
- Plan schema evolution

### Schema Updates

To update the labeling schema:

1. Update `labeling-schema.yaml`
2. Test changes in development environment
3. Update Kyverno policies if needed
4. Roll out changes gradually
5. Update documentation and training materials

## Cost Reporting Integration

### Grafana Dashboards

Labels enable rich cost visualization in Grafana:

```promql
# Cost by team over time
sum by (team) (
  kube_pod_container_resource_requests{resource="cpu"} *
  on(pod) group_left(team) kube_pod_labels{label_team!=""}
)

# Cost by pipeline
sum by (pipeline) (
  kube_pod_container_resource_requests{resource="memory"} *
  on(pod) group_left(pipeline) kube_pod_labels{label_pipeline!=""}
)
```

### CloudWatch/DataDog Integration

Labels can be exported to cloud monitoring systems:

```yaml
# Example CloudWatch exporter configuration
exporters:
  cloudwatch:
    namespace: NeuroNews/K8s
    dimensions:
      - name: Team
        value: '{{ .labels.team }}'
      - name: Pipeline  
        value: '{{ .labels.pipeline }}'
      - name: Environment
        value: '{{ .labels.env }}'
```

## API Reference

### Label Validation API

Query label compliance programmatically:

```bash
# Check if labels are valid
curl -X POST http://kyverno-api:8080/validate \
  -H "Content-Type: application/json" \
  -d '{
    "labels": {
      "app": "my-app",
      "component": "backend", 
      "pipeline": "api",
      "team": "my-team",
      "env": "prod",
      "cost_center": "product"
    }
  }'
```

### Cost Allocation API

Query costs by label dimensions:

```bash
# Get cost by team for last 7 days
curl "http://opencost:9003/allocation?window=7d&aggregate=label:team&format=json"

# Get detailed breakdown by multiple dimensions
curl "http://opencost:9003/allocation?window=1d&aggregate=label:team,label:pipeline&includeIdle=false"
```

## Security Considerations

### RBAC Integration

Grant teams access only to their labeled resources:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-neuronews-access
  namespace: neuronews
subjects:
- kind: User
  name: neuronews-team
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
---
# Network policy based on labels
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: team-isolation
spec:
  podSelector:
    matchLabels:
      team: neuronews
  policyTypes:
  - Ingress
  - Egress
```

### Audit Logging

Monitor label changes for compliance:

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: Metadata
  resources:
  - group: apps
    resources: ["deployments", "statefulsets"]
  omitStages:
  - RequestReceived
  namespaces: ["neuronews", "monitoring", "data-processing"]
```

## Best Practices

### Label Naming

- Use lowercase with hyphens for multi-word values
- Keep labels concise but descriptive
- Avoid special characters except hyphens
- Use consistent naming patterns across teams

### Cost Attribution

- Align cost centers with business reporting structure
- Group related components under same cost center
- Use pipeline labels to track data flow costs
- Regular reconciliation with finance team

### Governance

- Establish change management process for schema updates
- Document exemption criteria and approval process
- Regular training for development teams
- Automated compliance monitoring and alerting

## Related Documentation

- [OpenCost FinOps Integration](./opencost.md)
- [CDC Streaming Observability](../docs/cdc/observability.md)
- [Kubernetes Cost Optimization](../docs/finops/cost-optimization.md)
- [Monitoring and Alerting](../docs/monitoring/overview.md)
