# VPA Rightsizing Implementation for NeuroNews

Issue #340: Rightsizing: introduce VPA for ingestion & dbt jobs

This document describes the Vertical Pod Autoscaler (VPA) implementation for automated resource rightsizing of ingestion and dbt pipeline components.

## 🎯 Overview

VPA automatically adjusts CPU and memory requests/limits for pods based on actual resource usage patterns, reducing idle spend and improving resource utilization.

### Phased Implementation Approach

1. **Phase 1 (Recommendations Only)**: 1-2 weeks with `updateMode: "Off"`
2. **Phase 2 (Automatic Updates)**: Switch to `updateMode: "Auto"` for proven workloads

## 🏗 Architecture

### VPA Components

- **VPA Recommender**: Analyzes resource usage and generates recommendations
- **VPA Updater**: Applies recommendations by evicting and recreating pods
- **VPA Admission Controller**: Intercepts pod creation to apply recommendations

### Target Workloads

#### Ingestion Pipeline
- `neuronews-ingestion`: Article ingestion service
- `neuronews-consumer`: Message queue consumer
- `neuronews-article-processor`: Article processing worker
- `airflow-worker`: Airflow task execution (if using Kubernetes executor)
- `spark-driver`: Spark job coordination

#### DBT Pipeline
- `dbt-runner`: Daily DBT model execution
- `dbt-test-runner`: DBT test execution
- `dbt-docs-server`: Documentation server
- `dbt-spark-executor`: Spark-based DBT execution
- `dbt-metadata-processor`: Metadata extraction and processing

## 📁 File Structure

```
k8s/autoscaling/
├── vpa-crd.yaml                    # VPA Custom Resource Definitions
├── vpa-rbac.yaml                   # RBAC configuration for VPA components
├── vpa-deployment.yaml             # VPA controller deployments
├── vpa-ingestion-pipeline.yaml     # VPA objects for ingestion workloads
├── vpa-dbt-pipeline.yaml          # VPA objects for DBT workloads
├── install-vpa-rightsizing.sh     # Installation and configuration script
└── test-vpa-rightsizing.sh        # Comprehensive test suite

k8s/monitoring/
└── prometheus-vpa-rules.yaml      # VPA monitoring and alerting rules
```

## 🚀 Installation

### Prerequisites

- Kubernetes cluster with metrics-server deployed
- Prometheus for enhanced metrics (optional but recommended)
- kubectl access with cluster-admin permissions

### Phase 1: Recommendations Only

```bash
# Install VPA components and configure in recommendations-only mode
./k8s/autoscaling/install-vpa-rightsizing.sh

# Verify installation
kubectl get pods -n vpa-system
kubectl get vpa -n data-pipeline
```

### Phase 2: Enable Automatic Updates

After monitoring recommendations for 1-2 weeks:

```bash
# Switch to automatic mode
PHASE=auto ./k8s/autoscaling/install-vpa-rightsizing.sh
```

## 📊 Monitoring & Metrics

### Key Metrics (DoD Requirements)

1. **CPU/Memory Utilization Improvement**
   ```promql
   # CPU utilization efficiency
   vpa:container_allocation_efficiency:ratio{resource="cpu"}
   
   # Memory utilization efficiency  
   vpa:container_allocation_efficiency:ratio{resource="memory"}
   ```

2. **Resource Allocation Reduction**
   ```promql
   # Container CPU allocation changes
   rate(kube_pod_container_resource_requests{resource="cpu"}[1h])
   
   # Container memory allocation changes
   rate(kube_pod_container_resource_requests{resource="memory"}[1h])
   ```

3. **Pipeline Coverage**
   ```promql
   # VPA coverage by pipeline
   vpa:pipeline_coverage:ratio
   ```

### VPA-Specific Metrics

```promql
# VPA recommendation availability
vpa_last_recommendation_timestamp

# VPA update mode status
vpa_spec_update_policy_update_mode

# VPA recommendation values
vpa_status_recommendation_cpu_target
vpa_status_recommendation_memory_target
```

### Cost Impact Tracking

```promql
# Monthly cost savings from VPA optimization
vpa:cost_impact:monthly_savings

# Resource efficiency improvements
vpa:utilization_improvement:cpu
vpa:utilization_improvement:memory
```

## 🔍 Monitoring VPA Recommendations

### Check VPA Status

```bash
# List all VPA objects
kubectl get vpa -n data-pipeline -o wide

# Detailed VPA recommendations
kubectl describe vpa neuronews-ingestion-vpa -n data-pipeline

# VPA recommendation output format
kubectl get vpa neuronews-ingestion-vpa -n data-pipeline -o jsonpath='{.status.recommendation}'
```

### Sample VPA Recommendation

```yaml
recommendation:
  containerRecommendations:
  - containerName: ingestion
    lowerBound:
      cpu: 50m
      memory: 128Mi
    target:
      cpu: 100m
      memory: 256Mi
    uncappedTarget:
      cpu: 95m
      memory: 245Mi
    upperBound:
      cpu: 200m
      memory: 512Mi
```

### Resource Usage Analysis

```bash
# Current resource requests vs usage
kubectl top pods -n data-pipeline --sort-by=memory
kubectl top pods -n data-pipeline --sort-by=cpu

# Resource allocation vs recommendations gap
kubectl get pods -n data-pipeline -o custom-columns="NAME:.metadata.name,CPU-REQ:.spec.containers[0].resources.requests.cpu,MEM-REQ:.spec.containers[0].resources.requests.memory"
```

## 📈 Expected Outcomes

### Performance Improvements

1. **Reduced Resource Waste**
   - CPU allocation optimization: 15-30% reduction in over-provisioned resources
   - Memory allocation optimization: 20-40% reduction in unused memory

2. **Improved Utilization**
   - Target CPU utilization: 60-80% (from typical 20-40%)
   - Target memory utilization: 70-85% (from typical 30-50%)

3. **Cost Optimization**
   - Estimated monthly savings: 15-25% on compute costs
   - Reduced node requirements through better resource packing

### Operational Benefits

1. **Automated Rightsizing**: No manual resource tuning required
2. **Adaptive Scaling**: Automatic adjustment to workload changes
3. **Performance Stability**: Maintains application performance while optimizing resources

## 🚨 Alerts & Notifications

### VPA Health Alerts

- `VPAComponentDown`: VPA system component failures
- `VPARecommendationMissing`: Missing recommendations for >1 hour
- `VPAHighErrorRate`: VPA error rate >10%

### Resource Optimization Alerts

- `VPAResourceAllocationImproved`: Successful efficiency improvements
- `VPAResourceAllocationReduced`: Successful resource reductions
- `VPAUtilizationSustainedImprovement`: 24h+ sustained improvements

### Coverage Monitoring

- `VPAPipelineCoverageIncomplete`: <80% VPA coverage for pipeline

## 🔧 Configuration Examples

### VPA Resource Policy

```yaml
resourcePolicy:
  containerPolicies:
  - containerName: ingestion
    minAllowed:
      cpu: 100m      # Minimum safe CPU
      memory: 128Mi  # Minimum safe memory
    maxAllowed:
      cpu: 2000m     # Maximum allowed CPU
      memory: 4Gi    # Maximum allowed memory
    controlledResources: ["cpu", "memory"]
    controlledValues: RequestsAndLimits
```

### Update Policies

```yaml
updatePolicy:
  updateMode: "Off"    # Recommendations only
  # updateMode: "Auto"   # Automatic updates (Phase 2)
  # updateMode: "Initial" # Only on pod creation
```

## 🛠 Troubleshooting

### Common Issues

#### No Recommendations Generated

```bash
# Check VPA recommender logs
kubectl logs -n vpa-system deployment/vpa-recommender

# Verify metrics availability
kubectl top pods -n data-pipeline

# Check VPA object configuration
kubectl describe vpa <vpa-name> -n data-pipeline
```

#### Recommendations Not Applied

```bash
# Check VPA updater logs
kubectl logs -n vpa-system deployment/vpa-updater

# Verify update mode
kubectl get vpa <vpa-name> -n data-pipeline -o jsonpath='{.spec.updatePolicy.updateMode}'

# Check for resource constraints
kubectl describe vpa <vpa-name> -n data-pipeline | grep -A 10 "Resource Policy"
```

#### High Resource Recommendations

```bash
# Check historical usage patterns
kubectl describe vpa <vpa-name> -n data-pipeline | grep -A 20 "Container Recommendations"

# Review resource policy constraints
kubectl get vpa <vpa-name> -n data-pipeline -o yaml | grep -A 20 "resourcePolicy"
```

### Rollback Procedures

#### Disable VPA Temporarily

```bash
# Switch to Off mode
kubectl patch vpa <vpa-name> -n data-pipeline --type='merge' -p='{"spec":{"updatePolicy":{"updateMode":"Off"}}}'
```

#### Restore Original Resources

```bash
# Update deployment with previous resource requests
kubectl patch deployment <deployment-name> -n data-pipeline --type='merge' -p='{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"requests":{"cpu":"<previous-cpu>","memory":"<previous-memory>"}}}]}}}}'
```

## 📋 Validation Checklist

### Phase 1 (Recommendations Only)

- [ ] VPA CRDs and controllers deployed
- [ ] VPA objects created with `updateMode: "Off"`
- [ ] VPA recommendations visible for target workloads
- [ ] Monitoring alerts configured and firing
- [ ] Baseline resource usage documented

### Phase 2 (Automatic Updates)

- [ ] VPA switched to `updateMode: "Auto"`
- [ ] Resource allocation changes observed
- [ ] CPU/memory utilization improved
- [ ] Application performance maintained
- [ ] Cost savings documented

### Success Criteria (DoD)

- [ ] **VPA recommendations visible**: `kubectl describe vpa` shows target/upperBound/lowerBound
- [ ] **Sustained CPU/memory utilization improves**: >15% efficiency improvement
- [ ] **Container allocation falls**: Resource requests optimized based on actual usage
- [ ] **Monitoring integration**: Prometheus alerts and Grafana dashboards functional

## 🔗 Integration Points

### Existing FinOps Stack

- **Prometheus**: Enhanced metrics collection and VPA monitoring
- **Grafana**: VPA efficiency dashboards and cost impact visualization
- **OpenCost**: Resource cost tracking and VPA savings calculation
- **Alertmanager**: VPA health and optimization notifications

### CI/CD Integration

- **Resource Testing**: Validate VPA recommendations in staging
- **Performance Testing**: Ensure application stability with VPA adjustments
- **Cost Tracking**: Monitor VPA impact on infrastructure costs

## 📚 References

- **Kubernetes VPA Documentation**: https://kubernetes.io/docs/concepts/workloads/autoscaling/
- **VPA GitHub Repository**: https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler
- **VPA Best Practices**: https://cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler
- **FinOps Dashboard**: http://grafana:3000/d/neuronews-finops/
- **VPA Monitoring**: http://prometheus:9090/graph
- **Budget Alerts Runbook**: docs/runbooks/finops-budget-alerts.md

## 🏃‍♂️ Quick Start Commands

```bash
# 1. Install VPA in recommendations mode
./k8s/autoscaling/install-vpa-rightsizing.sh

# 2. Monitor recommendations for 1-2 weeks
kubectl get vpa -n data-pipeline -o wide
kubectl describe vpa neuronews-ingestion-vpa -n data-pipeline

# 3. Switch to automatic mode when ready
PHASE=auto ./k8s/autoscaling/install-vpa-rightsizing.sh

# 4. Monitor resource optimization
kubectl top pods -n data-pipeline
# Check FinOps dashboard for cost impact
```
