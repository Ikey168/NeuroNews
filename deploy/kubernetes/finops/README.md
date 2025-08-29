# NeuroNews FinOps Labeling Governance

A comprehensive Kubernetes cost allocation and governance system using standardized labels enforced by Kyverno policies.

## 🎯 Overview

This system ensures accurate cost attribution and financial visibility across all Kubernetes workloads by:

- **Enforcing standardized labels** for cost allocation across teams and business units
- **Automating governance** through Kyverno policies that block non-compliant resources
- **Enabling financial visibility** with detailed cost breakdown by team, pipeline, and environment
- **Integrating with OpenCost** for real-time cost monitoring and reporting

## 📋 Required Labels Schema

All workloads must include these six labels:

| Label | Type | Description | Examples |
|-------|------|-------------|----------|
| `app` | string | Application name | `neuronews-api`, `kafka-connect` |
| `component` | string | Component type | `backend`, `frontend`, `database` |
| `pipeline` | enum | Business function | `ingest`, `transform`, `api`, `rag` |
| `team` | string | Owning team | `neuronews`, `data-engineering` |
| `env` | enum | Environment | `dev`, `staging`, `prod`, `test` |
| `cost_center` | string | Cost center | `product`, `data-platform` |

### Pipeline Values
- `ingest` - Data ingestion (Kafka, scrapers)
- `transform` - Data processing (Spark, ETL)
- `dbt` - DBT transformations
- `api` - API services (REST, GraphQL)
- `rag` - ML inference (LLM, embeddings)
- `monitoring` - Observability (Prometheus, Grafana)
- `infra` - Platform services (operators, controllers)

## 🚀 Quick Start

### Installation

```bash
# Install FinOps labeling governance
cd k8s/finops
./install.sh

# Verify installation
./install.sh validate

# Run test suite
./test.sh

# Run interactive demo
python3 ../../demo_finops_labeling_governance.py
```

### Example Workload

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-service
  labels:
    app: my-service
    component: backend
    pipeline: api
    team: neuronews
    env: prod
    cost_center: product
spec:
  template:
    metadata:
      labels:
        app: my-service
        component: backend
        pipeline: api
        team: neuronews
        env: prod
        cost_center: product
    # ... rest of spec
```

## 📁 File Structure

```
k8s/finops/
├── install.sh                 # Installation script
├── test.sh                   # Test suite
├── kyverno-policies.yaml     # Governance policies
├── labeling-schema.yaml      # Schema definition
├── kustomization.yaml        # Kustomize overlay
└── patches/                  # Label patches
    ├── kafka-labels.yaml
    ├── spark-labels.yaml
    ├── api-labels.yaml
    └── monitoring-labels.yaml

docs/finops/
└── labels.md                 # Comprehensive documentation

demo_finops_labeling_governance.py  # Interactive demo
```

## 🔧 Components

### Kyverno Policies

1. **require-finops-labels** - Enforces presence of all required labels
2. **validate-finops-label-values** - Validates enum values (pipeline, env)
3. **generate-missing-finops-labels** - Auto-generates defaults by namespace

### Kustomize Overlays

- Patches existing workloads with appropriate labels
- Organized by workload type (kafka, spark, api, monitoring)
- Non-destructive patching that preserves existing labels

### Installation Script

- Automated installation with prerequisite checks
- Supports audit mode for gradual rollout
- Built-in validation and compliance reporting

## 📊 Cost Allocation Examples

### By Team
```bash
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.labels.team}{"\t"}{.metadata.name}{"\n"}{end}' | sort
```

### By Pipeline
```bash
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.labels.pipeline}{"\t"}{.metadata.name}{"\n"}{end}' | sort
```

### OpenCost Integration
```bash
# Cost by team (last 7 days)
curl "http://opencost:9003/allocation?window=7d&aggregate=label:team"

# Multi-dimensional breakdown
curl "http://opencost:9003/allocation?window=7d&aggregate=label:team,label:pipeline,label:env"
```

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Full test suite
./test.sh

# Individual test components
./test.sh setup    # Setup test environment only
./test.sh cleanup  # Cleanup test environment only
```

Test coverage includes:
- Policy installation validation
- Label enforcement testing
- Invalid value rejection
- Performance impact assessment
- Compliance reporting

## 🎭 Demo

Interactive demonstration of the complete system:

```bash
# Run full demo with cleanup
python3 demo_finops_labeling_governance.py

# Run demo without cleanup (for inspection)
python3 demo_finops_labeling_governance.py --no-cleanup
```

Demo scenarios:
1. Valid workload deployment
2. Invalid workload blocking
3. Invalid label value rejection
4. Cost allocation views
5. Compliance reporting
6. OpenCost integration

## 🔒 Security & Governance

### RBAC Integration
Labels enable team-based access control:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-access
roleRef:
  kind: ClusterRole
  name: edit
subjects:
- kind: User
  name: team-member
```

### Network Policies
Team isolation using labels:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
spec:
  podSelector:
    matchLabels:
      team: neuronews
```

## 🛠 Troubleshooting

### Common Issues

**Missing Labels Error**:
```bash
# Add required labels to existing deployment
kubectl patch deployment my-app -p '{"metadata":{"labels":{"app":"my-app","team":"my-team","pipeline":"api","env":"prod","cost_center":"product","component":"backend"}}}'
```

**Invalid Pipeline Value**:
```bash
# Fix invalid pipeline value
kubectl patch deployment my-app -p '{"metadata":{"labels":{"pipeline":"api"}}}'
```

**Policy Blocking Deployment**:
```bash
# Check policy events
kubectl get events --field-selector reason=PolicyViolation

# Temporarily disable enforcement (emergency only)
kubectl patch clusterpolicy require-finops-labels --type='merge' -p='{"spec":{"validationFailureAction":"audit"}}'
```

### Debug Commands

```bash
# View policy status
kubectl get clusterpolicy

# Check recent policy events
kubectl get events --sort-by='.lastTimestamp' | grep -i policy

# Generate compliance report
./install.sh report

# Test deployment with dry-run
kubectl apply --dry-run=server -f my-deployment.yaml
```

## 🔄 Migration Strategy

### Phase 1: Audit (2 weeks)
- Install policies in audit mode
- Monitor violations without blocking
- Generate compliance reports

### Phase 2: Label Application (2 weeks)
- Apply Kustomize overlays to existing workloads
- Update deployment templates
- Train teams on requirements

### Phase 3: Enforcement (1 week)
- Enable enforce mode
- Monitor for blocked deployments
- Handle exemption requests

## 📈 Monitoring & Alerting

### Grafana Dashboards

Cost trends by dimension:
```promql
# CPU cost by team
sum by (team) (
  kube_pod_container_resource_requests{resource="cpu"} *
  on(pod) group_left(team) kube_pod_labels{label_team!=""}
)
```

### Policy Compliance Alerts

```yaml
# Prometheus alert for policy violations
- alert: FinOpsLabelingViolation
  expr: increase(kyverno_policy_violation_total[5m]) > 0
  labels:
    severity: warning
  annotations:
    summary: "FinOps labeling policy violation detected"
```

## 🔗 Integration Points

- **OpenCost**: Automatic cost allocation by labels
- **Grafana**: Cost visualization dashboards  
- **Prometheus**: Policy compliance metrics
- **Kyverno**: Governance policy enforcement
- **Kustomize**: Non-destructive workload patching

## 📚 Related Documentation

- [OpenCost FinOps Integration](../../docs/finops/opencost.md)
- [CDC Streaming Observability](../../docs/cdc/observability.md)
- [Kubernetes Cost Optimization](../../docs/finops/cost-optimization.md)
- [Monitoring and Alerting](../../docs/monitoring/overview.md)

## 💡 Best Practices

1. **Consistent Naming**: Use lowercase with hyphens
2. **Business Alignment**: Map cost centers to financial reporting
3. **Regular Reviews**: Monthly cost allocation reviews
4. **Team Training**: Educate teams on labeling requirements
5. **Gradual Rollout**: Use audit mode before enforcement
6. **Exception Handling**: Document exemption process

## 📞 Support

For issues with the FinOps labeling system:

1. Check the troubleshooting section above
2. Run `./install.sh validate` for diagnostics  
3. Generate compliance report with `./install.sh report`
4. Review policy events: `kubectl get events --field-selector reason=PolicyViolation`

---

**Version**: 1.0  
**Last Updated**: 2024-01-01  
**Maintainer**: Platform Team
