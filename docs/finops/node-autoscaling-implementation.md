# Node Autoscaling & Bin-Packing Guardrails Implementation

Issue #341: Node autoscaling & bin-packing guardrails (cost-saver)

This document describes the implementation of node autoscaling and bin-packing guardrails for the NeuroNews Kubernetes cluster, delivering immediate cost savings through intelligent scaling and workload placement.

## 🎯 Overview

This implementation introduces comprehensive node autoscaling with bin-packing optimization to achieve significant cost reductions while maintaining application performance and reliability.

### Core Benefits

- **30-60% cost reduction** for batch workloads through spot instance usage
- **Improved resource utilization** through intelligent bin-packing
- **Automatic scaling** based on actual demand patterns
- **Fault-tolerant** workload distribution across availability zones

### Implementation Strategy

1. **Scale down fast**: Aggressive scaling policies to minimize idle resources
2. **Bin-pack well**: Topology constraints and priority classes for optimal placement
3. **Immediate savings**: Spot instances for non-critical workloads

## 🏗 Architecture Components

### Cluster Autoscaler Configuration

The Cluster Autoscaler is configured with cost-optimized settings:

- **Scale-down enabled**: Removes underutilized nodes after 5 minutes
- **Utilization threshold**: 50% threshold for scale-down decisions
- **Least-waste expander**: Optimizes for cost efficiency
- **Node group auto-discovery**: Automatic detection of scalable node groups

### Priority Classes Hierarchy

```yaml
neuronews-critical (1000) # Critical ingestion components
neuronews-standard (500)  # Standard pipeline workloads (default)
neuronews-batch (100)     # Batch jobs and processing
neuronews-dev (50)        # Development and testing
neuronews-spot (25)       # Spot instance tolerant workloads
```

### Node Pool Strategy

#### On-Demand Pool (Critical Workloads)
- **Instance types**: m5.large, m5.xlarge, c5.large, c5.xlarge
- **Scaling**: 2-10 nodes (min-max)
- **Purpose**: High-priority, latency-sensitive workloads
- **Labels**: `node-lifecycle=on-demand`, `node-type=critical`

#### Spot Pool (Batch Workloads)
- **Instance types**: m5.large-2xlarge, c5.large-2xlarge, r5.large-xlarge
- **Scaling**: 0-20 nodes (elastic)
- **Purpose**: Batch jobs, data processing, development
- **Labels**: `node-lifecycle=spot`, `node-type=batch`
- **Taints**: `node-lifecycle=spot:NoSchedule`

## 📁 File Structure

```
k8s/autoscaling/
├── cluster-autoscaler.yaml        # Cluster Autoscaler deployment with cost optimization
├── priority-classes.yaml          # Priority classes for workload prioritization
├── bin-packing-guardrails.yaml   # Pod Disruption Budgets and topology constraints
├── spot-node-pools.yaml          # Spot instance node pool configurations
├── workload-examples.yaml        # Example deployments with optimizations
├── install-node-autoscaling.sh   # Installation script with validation
└── test-node-autoscaling.sh      # Comprehensive test suite

k8s/monitoring/
└── prometheus-autoscaling-rules.yaml # Monitoring rules for cost tracking
```

## 🚀 Installation

### Prerequisites

- Kubernetes cluster with metrics-server
- AWS CLI with EKS permissions
- kubectl with cluster-admin access
- Prometheus for monitoring (recommended)

### Quick Installation

```bash
# Install all components
./k8s/autoscaling/install-node-autoscaling.sh

# Dry run first (recommended)
./k8s/autoscaling/install-node-autoscaling.sh --dry-run

# Custom configuration
./k8s/autoscaling/install-node-autoscaling.sh \
  --cluster production-cluster \
  --region us-west-2 \
  --namespace data-pipeline
```

### Manual Node Group Creation

After running the installation script, create AWS EKS managed node groups:

#### Option 1: AWS CLI
```bash
# Extract AWS CLI commands from configuration
kubectl get configmap spot-node-pool-config -n kube-system \
  -o jsonpath='{.data.aws-cli-commands\.sh}' > create-node-groups.sh

# Edit script to update ACCOUNT_ID and subnet IDs
vim create-node-groups.sh

# Execute
chmod +x create-node-groups.sh
./create-node-groups.sh
```

#### Option 2: Terraform
```hcl
# Add to your Terraform configuration
resource "aws_eks_node_group" "spot_batch" {
  cluster_name    = "neuronews-cluster"
  node_group_name = "neuronews-spot-batch"
  capacity_type   = "SPOT"
  instance_types  = ["m5.large", "m5.xlarge", "c5.large", "c5.xlarge"]
  
  scaling_config {
    desired_size = 0
    max_size     = 20
    min_size     = 0
  }
  
  # See spot-node-pools.yaml for complete configuration
}
```

## 📊 Workload Optimization Patterns

### Critical Workloads (Always Available)

```yaml
spec:
  priorityClassName: neuronews-critical
  
  # Resource requests for proper bin-packing
  containers:
  - resources:
      requests:
        cpu: 200m
        memory: 512Mi
      limits:
        cpu: 500m
        memory: 1Gi
  
  # Prefer on-demand instances
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: node-lifecycle
            operator: In
            values: ["on-demand"]
  
  # Spread across zones for resilience
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
```

### Batch Workloads (Cost-Optimized)

```yaml
spec:
  priorityClassName: neuronews-batch
  
  # Tolerate spot instance interruptions
  tolerations:
  - key: "node-lifecycle"
    operator: "Equal"
    value: "spot"
    effect: "NoSchedule"
  - key: "node.kubernetes.io/not-ready"
    operator: "Exists"
    effect: "NoExecute"
    tolerationSeconds: 300
  
  # Prefer spot instances for cost savings
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: node-lifecycle
            operator: In
            values: ["spot"]
```

## 📈 Monitoring & Observability

### Key Metrics

#### Cost Optimization Metrics
```promql
# Hourly node costs by type
neuronews:cost:hourly_node_cost

# Daily savings potential from spot usage
neuronews:cost:daily_savings_potential

# Node count by lifecycle (on-demand vs spot)
neuronews:node_count:by_lifecycle
```

#### Resource Efficiency Metrics
```promql
# Node CPU utilization
neuronews:node_utilization:cpu

# Node memory utilization
neuronews:node_utilization:memory

# Resource efficiency by workload
neuronews:resource_efficiency:cpu
neuronews:resource_efficiency:memory
```

#### Bin-Packing Effectiveness
```promql
# Pod density per node
neuronews:binpacking:node_density

# Workload distribution by node type
neuronews:pod_distribution:by_node_type

# Priority class distribution
neuronews:pod_distribution:by_priority
```

### Alerts & Notifications

#### Cost Optimization Alerts
- **NodeUnderutilized**: Nodes with <20% CPU and <30% memory usage
- **LowPriorityPodsOnExpensiveNodes**: Batch workloads on on-demand instances
- **CostOptimizationActive**: Daily savings potential tracking

#### Operational Alerts
- **ClusterAutoscalerDown**: Autoscaler component failures
- **HighSpotInterruptionRate**: Excessive spot instance interruptions
- **PoorBinPacking**: Nodes with suboptimal pod density

#### Success Notifications
- **AutoscalingSuccessful**: Scale events with improved efficiency
- **BinPackingImproved**: High pod density achievements

### Dashboards

#### Cost Impact Dashboard
- Real-time cost savings visualization
- On-demand vs spot instance usage
- Resource allocation efficiency trends
- Monthly cost projections

#### Operational Dashboard
- Cluster autoscaler status and events
- Node scaling history and patterns
- Workload distribution by priority
- Resource utilization heatmaps

## 🔍 Validation & Testing

### Automated Testing

```bash
# Run comprehensive test suite
./k8s/autoscaling/test-node-autoscaling.sh

# Test specific components
./k8s/autoscaling/test-node-autoscaling.sh --cluster my-cluster
```

### Manual Validation

#### 1. Verify Cluster Autoscaler
```bash
# Check autoscaler status
kubectl logs -n kube-system deployment/cluster-autoscaler --tail=50

# Monitor scaling events
kubectl get events --field-selector involvedObject.kind=Node --sort-by='.firstTimestamp'

# Check node utilization
kubectl top nodes
```

#### 2. Validate Priority Classes
```bash
# List priority classes
kubectl get priorityclass

# Check workload priorities
kubectl get pods -o custom-columns="NAME:.metadata.name,PRIORITY:.spec.priorityClassName,NODE:.spec.nodeName"
```

#### 3. Monitor Spot Instance Usage
```bash
# Check node labels
kubectl get nodes -l node-lifecycle=spot --show-labels

# Verify workload placement
kubectl get pods -o wide | grep batch
```

#### 4. Assess Bin-Packing
```bash
# Pod distribution across nodes
kubectl get pods -o wide --all-namespaces | awk '{print $8}' | sort | uniq -c

# Node resource allocation
kubectl describe nodes | grep -E "(Name:|Allocated resources:)" -A 5
```

## 🎯 DoD Requirements Validation

### ✅ Scale-down occurs after idle

**Implementation**: Cluster Autoscaler configured with:
- `--scale-down-enabled=true`
- `--scale-down-unneeded-time=5m`
- `--scale-down-utilization-threshold=0.5`

**Validation**: 
```bash
# Monitor scale-down events
kubectl logs -n kube-system deployment/cluster-autoscaler | grep "scale down"

# Check node lifecycle
kubectl get events --field-selector reason=NodeDeleted
```

### ✅ Workloads respect priorities

**Implementation**: 
- 5-tier priority class system
- Pod Disruption Budgets for critical workloads
- Priority-based eviction policies

**Validation**:
```bash
# Verify priority class usage
kubectl get pods --all-namespaces -o custom-columns="NAME:.metadata.name,PRIORITY:.spec.priorityClassName"

# Check eviction events
kubectl get events --field-selector reason=Evicted
```

### ✅ Spot pool handles batch jobs

**Implementation**:
- Dedicated spot node groups with taints
- Batch workloads with spot tolerations
- Cost-optimized instance type selection

**Validation**:
```bash
# Check spot node availability
kubectl get nodes -l node-lifecycle=spot

# Verify batch workload placement
kubectl get pods -l tier=batch -o wide
```

## 💰 Cost Impact Analysis

### Expected Savings

#### Compute Cost Reduction
- **Spot instances**: Up to 90% savings vs on-demand
- **Right-sizing**: 20-40% reduction in over-provisioned resources
- **Scale-down efficiency**: 30-50% reduction in idle resources

#### Operational Efficiency
- **Automatic scaling**: Eliminates manual intervention
- **Intelligent placement**: Maximizes resource utilization
- **Fault tolerance**: Maintains availability during spot interruptions

### ROI Calculation

```
Monthly compute baseline: $10,000
Spot instance usage (60% workloads): $6,000 → $600 (90% savings)
Right-sizing optimization (40% workloads): $4,000 → $2,800 (30% savings)
Total monthly savings: $6,600 (66% reduction)
Annual savings: $79,200
```

## 🔧 Troubleshooting

### Common Issues

#### Cluster Autoscaler Not Scaling
```bash
# Check autoscaler logs
kubectl logs -n kube-system deployment/cluster-autoscaler

# Verify node group tags
aws eks describe-nodegroup --cluster-name neuronews-cluster --nodegroup-name spot-batch

# Check resource quotas
kubectl describe limitrange -n data-pipeline
```

#### Pods Not Scheduling on Spot Instances
```bash
# Check node taints and tolerations
kubectl describe node <spot-node-name>

# Verify pod tolerations
kubectl describe pod <pod-name> | grep -A 10 "Tolerations:"

# Check node affinity
kubectl describe pod <pod-name> | grep -A 10 "Node-Selectors:"
```

#### High Spot Instance Interruptions
```bash
# Monitor interruption rate
kubectl get events --field-selector involvedObject.kind=Node,reason=NodeNotReady

# Check instance type diversity
kubectl get nodes -l node-lifecycle=spot -o custom-columns="NAME:.metadata.name,INSTANCE_TYPE:.metadata.labels.node\.kubernetes\.io/instance-type"

# Adjust tolerationSeconds for critical workloads
kubectl patch deployment my-app -p '{"spec":{"template":{"spec":{"tolerations":[{"key":"node.kubernetes.io/not-ready","operator":"Exists","effect":"NoExecute","tolerationSeconds":600}]}}}}'
```

#### Poor Bin-Packing Efficiency
```bash
# Analyze resource requests vs usage
kubectl top pods --all-namespaces --sort-by=memory

# Check pod anti-affinity rules
kubectl get pods -o yaml | grep -A 10 "podAntiAffinity:"

# Review topology spread constraints
kubectl describe pod <pod-name> | grep -A 5 "Topology Spread Constraints:"
```

### Performance Tuning

#### Optimize Autoscaler Settings
```yaml
# Faster scaling for development
--scale-down-delay-after-add=5m
--scale-down-unneeded-time=3m

# More conservative for production
--scale-down-delay-after-add=15m
--scale-down-unneeded-time=10m
```

#### Adjust Priority Thresholds
```yaml
# Increase batch priority for better scheduling
neuronews-batch: 200  # Was 100

# Lower dev priority for more aggressive eviction
neuronews-dev: 25     # Was 50
```

## 🚀 Future Enhancements

### Planned Improvements

1. **Predictive Scaling**: Machine learning-based demand forecasting
2. **Multi-Cloud Support**: Azure Spot VMs and GCP Preemptible instances
3. **Custom Metrics Scaling**: Application-specific scaling triggers
4. **Cost Allocation**: Detailed cost attribution by team/project

### Integration Opportunities

1. **GitOps Integration**: ArgoCD-based deployment of scaling policies
2. **Chaos Engineering**: Automated spot interruption testing
3. **FinOps Dashboard**: Real-time cost optimization metrics
4. **Policy Engine**: OPA-based admission control for resource efficiency

## 📚 References

- **AWS EKS Best Practices**: https://docs.aws.amazon.com/eks/latest/best-practices/cas.html
- **Cast AI Autoscaling Guide**: https://cast.ai/blog/eks-cluster-autoscaler-6-best-practices-for-effective-autoscaling/
- **Kubernetes Autoscaling**: https://kubernetes.io/docs/concepts/workloads/autoscaling/
- **Spot Instance Best Practices**: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html
- **Priority Classes**: https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/

## 🏃‍♂️ Quick Start Commands

```bash
# 1. Install node autoscaling and bin-packing guardrails
./k8s/autoscaling/install-node-autoscaling.sh

# 2. Create AWS node groups
kubectl get configmap spot-node-pool-config -n kube-system -o jsonpath='{.data.aws-cli-commands\.sh}' | bash

# 3. Deploy example workloads
kubectl apply -f k8s/autoscaling/workload-examples.yaml -n data-pipeline

# 4. Monitor effectiveness
kubectl logs -n kube-system deployment/cluster-autoscaler --tail=50
kubectl top nodes
kubectl get pods -o wide --all-namespaces | grep batch

# 5. Check cost impact
# Visit Grafana dashboard: http://grafana:3000/d/neuronews-finops-autoscaling/
```
