# OpenCost FinOps Integration

## Overview

OpenCost is an open-source CNCF project that provides real-time cost monitoring and allocation for Kubernetes workloads. This integration (Issue #402) enables comprehensive cost visibility for the NeuroNews platform, tracking costs per namespace, workload, and custom labels.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Kubernetes  │───▶│  OpenCost   │───▶│ Prometheus  │───▶│   Grafana   │
│  Metrics    │    │  Exporter   │    │  (Metrics)  │    │(Dashboard) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                    │                   │
       ▼                    ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ kube-state- │    │  OpenCost   │    │ Cost Alerts │
│  metrics    │    │    API      │    │ & Reports   │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Features

- **Real-time Cost Monitoring**: Track costs as resources are consumed
- **Multi-dimensional Allocation**: Costs by namespace, pod, service, deployment, label
- **Cloud Provider Integration**: Support for AWS, GCP, Azure, and on-premise
- **Historical Data**: Cost trends and usage patterns over time
- **API Access**: Programmatic access to cost and allocation data
- **Prometheus Integration**: Native metrics for alerting and dashboards

## Installation

### Prerequisites

- Kubernetes cluster with RBAC enabled
- Helm 3.x installed
- kubectl configured for cluster access
- Prometheus instance running in the cluster

### Quick Installation

```bash
# Clone the repository and navigate to OpenCost directory
cd k8s/opencost

# Run the automated installation script
./install.sh
```

### Manual Installation

```bash
# Add OpenCost Helm repository
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

# Install OpenCost with custom values
helm install opencost opencost/opencost \
  --namespace opencost \
  --create-namespace \
  --values values.yaml \
  --wait

# Verify installation
kubectl get pods -n opencost
kubectl get services -n opencost
```

### Configuration

The installation uses custom values in `k8s/opencost/values.yaml`:

```yaml
# Key configuration highlights
opencost:
  exporter:
    env:
      CLUSTER_ID: "neuronews-cluster"
      PROMETHEUS_SERVER_ENDPOINT: "http://prometheus:9090"
    persistence:
      enabled: true
      size: "0.2Gi"
  
  ui:
    enabled: true
    
prometheus:
  serviceMonitor:
    enabled: true
    interval: "1m"
```

## API Usage

### Access Methods

#### 1. Port Forward (Development)
```bash
# Forward OpenCost API port
kubectl port-forward -n opencost svc/opencost 9003:9003

# Forward OpenCost UI port
kubectl port-forward -n opencost svc/opencost-ui 9090:9090
```

#### 2. Service Access (Cluster Internal)
```bash
# API endpoint
http://opencost.opencost.svc.cluster.local:9003

# UI endpoint
http://opencost-ui.opencost.svc.cluster.local:9090
```

### API Endpoints

#### Cost Allocation API

Get cost allocation data for the last 7 days:
```bash
curl "http://localhost:9003/allocation?window=7d&aggregate=namespace"
```

**Example Response:**
```json
{
  "code": 200,
  "status": "success",
  "data": {
    "neuronews": {
      "name": "neuronews",
      "properties": {
        "cluster": "neuronews-cluster",
        "namespace": "neuronews"
      },
      "window": {
        "start": "2025-08-21T00:00:00Z",
        "end": "2025-08-28T00:00:00Z"
      },
      "start": "2025-08-21T00:00:00Z",
      "end": "2025-08-28T00:00:00Z",
      "minutes": 10080.0,
      "cpuCores": 2.5,
      "cpuCoreHours": 420.0,
      "cpuCost": 8.40,
      "cpuCostAdjustment": 0.0,
      "gpuCount": 0,
      "gpuHours": 0.0,
      "gpuCost": 0.0,
      "gpuCostAdjustment": 0.0,
      "ramBytes": 8589934592,
      "ramByteHours": 1439078342656.0,
      "ramCost": 5.76,
      "ramCostAdjustment": 0.0,
      "pvBytes": 107374182400,
      "pvByteHours": 18000000000000.0,
      "pvCost": 2.16,
      "pvCostAdjustment": 0.0,
      "networkCost": 0.0,
      "networkCostAdjustment": 0.0,
      "loadBalancerCost": 0.0,
      "loadBalancerCostAdjustment": 0.0,
      "sharedCost": 0.0,
      "externalCost": 0.0,
      "totalCost": 16.32,
      "totalEfficiency": 0.65
    }
  }
}
```

#### Aggregation Options

**By Namespace:**
```bash
curl "http://localhost:9003/allocation?window=24h&aggregate=namespace"
```

**By Deployment:**
```bash
curl "http://localhost:9003/allocation?window=24h&aggregate=deployment"
```

**By Pod:**
```bash
curl "http://localhost:9003/allocation?window=24h&aggregate=pod"
```

**By Service:**
```bash
curl "http://localhost:9003/allocation?window=24h&aggregate=service"
```

**By Custom Labels:**
```bash
curl "http://localhost:9003/allocation?window=24h&aggregate=label:app.kubernetes.io/component"
```

#### Assets API

Get cluster asset costs (nodes, storage, load balancers):
```bash
curl "http://localhost:9003/assets?window=7d&aggregate=type"
```

**Example Response:**
```json
{
  "code": 200,
  "status": "success",
  "data": {
    "Node": {
      "type": "Node",
      "count": 3,
      "cost": 504.00,
      "properties": {
        "category": "Compute",
        "provider": "aws",
        "service": "AmazonEC2"
      }
    },
    "PersistentVolume": {
      "type": "PersistentVolume", 
      "count": 5,
      "cost": 25.20,
      "properties": {
        "category": "Storage",
        "provider": "aws",
        "service": "AmazonEBS"
      }
    },
    "LoadBalancer": {
      "type": "LoadBalancer",
      "count": 2,
      "cost": 36.00,
      "properties": {
        "category": "Network",
        "provider": "aws",
        "service": "AmazonELB"
      }
    }
  }
}
```

#### Time Windows

Supported time window formats:
- `1h`, `24h`, `7d`, `30d` - Relative windows
- `2025-08-01T00:00:00Z,2025-08-07T23:59:59Z` - Absolute windows
- `today`, `yesterday`, `week`, `month` - Named windows

#### Filtering

**Filter by Namespace:**
```bash
curl "http://localhost:9003/allocation?window=24h&filter=namespace:neuronews"
```

**Filter by Label:**
```bash
curl "http://localhost:9003/allocation?window=24h&filter=label[app]:fastapi"
```

**Multiple Filters:**
```bash
curl "http://localhost:9003/allocation?window=24h&filter=namespace:neuronews,label[env]:production"
```

## Prometheus Metrics

OpenCost exposes the following key metrics to Prometheus:

### Cost Metrics

```prometheus
# Node hourly cost
node_total_hourly_cost{instance="node1", node="node1", provider_id="aws:///us-west-2a/i-1234567890abcdef0"}

# Container CPU allocation cost
container_cpu_allocation{container="fastapi", namespace="neuronews", node="node1", pod="fastapi-7d8f4b5c9-abc123"}

# Container memory allocation cost  
container_memory_allocation{container="fastapi", namespace="neuronews", node="node1", pod="fastapi-7d8f4b5c9-abc123"}

# Persistent volume cost
pv_hourly_cost{persistentvolume="pvc-1234567890abcdef", storageclass="gp2"}

# Network cost
network_zone_egress_cost{source_zone="us-west-2a", dest_zone="us-west-2b"}
```

### Efficiency Metrics

```prometheus
# CPU efficiency (utilization vs allocation)
container_cpu_efficiency{container="fastapi", namespace="neuronews"}

# Memory efficiency
container_memory_efficiency{container="fastapi", namespace="neuronews"}

# Overall cost efficiency
allocation_efficiency{namespace="neuronews"}
```

### Example Queries

**Total cluster cost per hour:**
```prometheus
sum(node_total_hourly_cost)
```

**Cost by namespace:**
```prometheus
sum by (namespace) (container_cpu_allocation + container_memory_allocation)
```

**Most expensive pods:**
```prometheus
topk(10, sum by (pod, namespace) (container_cpu_allocation + container_memory_allocation))
```

**CPU efficiency by namespace:**
```prometheus
avg by (namespace) (container_cpu_efficiency)
```

## Dashboards and Alerting

### Grafana Dashboard Queries

**Daily Cost Trend:**
```prometheus
sum(increase(node_total_hourly_cost[24h])) by (day)
```

**Namespace Cost Breakdown:**
```prometheus
sum by (namespace) (
  container_cpu_allocation + 
  container_memory_allocation + 
  pv_hourly_cost
)
```

**Cost per Request (combine with application metrics):**
```prometheus
sum(container_cpu_allocation + container_memory_allocation) / 
sum(increase(http_requests_total[1h]))
```

### Alerting Rules

```yaml
# Example Prometheus alerting rules
groups:
  - name: opencost-finops
    rules:
      - alert: HighNamespaceCost
        expr: sum by (namespace) (container_cpu_allocation + container_memory_allocation) > 100
        for: 1h
        labels:
          severity: warning
          team: finops
        annotations:
          summary: "High cost detected for namespace {{ $labels.namespace }}"
          description: "Namespace {{ $labels.namespace }} cost is ${{ $value }}/hour"
          
      - alert: LowResourceEfficiency
        expr: avg by (namespace) (container_cpu_efficiency) < 0.3
        for: 2h
        labels:
          severity: warning
          team: engineering
        annotations:
          summary: "Low resource efficiency in {{ $labels.namespace }}"
          description: "CPU efficiency is {{ $value | humanizePercentage }} in namespace {{ $labels.namespace }}"
```

## Advanced Usage

### Custom Cost Models

Create custom pricing for on-premise or private cloud:

```yaml
# Custom pricing ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: custom-pricing-model
  namespace: opencost
data:
  config.yaml: |
    CPU: 0.02  # $0.02 per vCPU hour
    RAM: 0.01  # $0.01 per GB hour
    GPU: 2.50  # $2.50 per GPU hour
    storage: 0.0001  # $0.0001 per GB hour
    spot:
      CPU: 0.01  # 50% discount for spot instances
      RAM: 0.005
```

### Network Cost Tracking

Enable network cost monitoring for inter-zone traffic:

```yaml
# In values.yaml
networkCosts:
  enabled: true
  config:
    internetEgressCost: 0.09  # $0.09 per GB
    regionEgressCost: 0.02    # $0.02 per GB
    zoneEgressCost: 0.01      # $0.01 per GB
```

### Cloud Provider Integration

#### AWS Integration

```bash
# Set up AWS cost data integration
kubectl create secret generic aws-cost-secret \
  --from-literal=AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  --from-literal=AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  --namespace opencost

# Update values.yaml
env:
  CLOUD_PROVIDER_API_KEY: "set-via-secret"
  AWS_REGION: "us-west-2"
```

#### Multi-Cloud Setup

```yaml
# Configure multiple cloud providers
env:
  CLOUD_PROVIDER_API_KEY: "set-via-secret"
  MULTI_CLOUD_BASIC_AUTH: "user:password"
  AZURE_SUBSCRIPTION_ID: "subscription-id"
  GCP_PROJECT_ID: "project-id"
```

## Troubleshooting

### Common Issues

#### 1. No Cost Data Appearing

**Symptoms:** API returns empty data or zeros
**Solutions:**
```bash
# Check if metrics are being collected
kubectl logs -n opencost deployment/opencost

# Verify Prometheus connectivity
curl http://localhost:9003/healthz

# Check if kube-state-metrics is running
kubectl get pods -n kube-system | grep kube-state-metrics
```

#### 2. Prometheus Integration Issues

**Symptoms:** Metrics not visible in Prometheus
**Solutions:**
```bash
# Check ServiceMonitor (if using Prometheus Operator)
kubectl get servicemonitor -n opencost

# Verify scrape configuration
kubectl get configmap prometheus-config -n monitoring -o yaml

# Test metrics endpoint
curl http://opencost.opencost.svc.cluster.local:9003/metrics
```

#### 3. High Memory Usage

**Symptoms:** OpenCost pod using excessive memory
**Solutions:**
```bash
# Increase memory limits
kubectl patch deployment opencost -n opencost -p '{"spec":{"template":{"spec":{"containers":[{"name":"opencost","resources":{"limits":{"memory":"2Gi"}}}]}}}}'

# Enable data retention limits
kubectl set env deployment/opencost -n opencost MAX_QUERY_CONCURRENCY=5
```

### Health Checks

```bash
# Check pod status
kubectl get pods -n opencost

# Check service endpoints
kubectl get endpoints -n opencost

# Test API health
curl http://localhost:9003/healthz

# View logs
kubectl logs -n opencost deployment/opencost --follow
```

### Performance Tuning

```yaml
# Optimize for large clusters
env:
  MAX_QUERY_CONCURRENCY: "10"
  QUERY_TIMEOUT: "300s"
  CACHE_TTL: "10m"
  LOG_LEVEL: "info"
  
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "2"
    memory: "4Gi"
```

## Integration with NeuroNews

### Namespace Cost Tracking

Monitor costs for NeuroNews components:

```bash
# NeuroNews application costs
curl "http://localhost:9003/allocation?window=7d&filter=namespace:neuronews"

# Monitoring infrastructure costs
curl "http://localhost:9003/allocation?window=7d&filter=namespace:monitoring"

# Data processing costs (Spark, Kafka)
curl "http://localhost:9003/allocation?window=7d&filter=label[component]:data-processing"
```

### Cost Optimization Queries

```bash
# Identify underutilized resources
curl "http://localhost:9003/allocation?window=24h&aggregate=pod" | jq '.data[] | select(.totalEfficiency < 0.3)'

# Most expensive services
curl "http://localhost:9003/allocation?window=7d&aggregate=service" | jq 'to_entries | sort_by(.value.totalCost) | reverse | .[0:5]'

# Cost per user/request (combine with application metrics)
COST=$(curl -s "http://localhost:9003/allocation?window=1h&filter=namespace:neuronews" | jq '.data[].totalCost // 0')
REQUESTS=$(curl -s "http://prometheus:9090/api/v1/query?query=sum(increase(http_requests_total{namespace=\"neuronews\"}[1h]))" | jq '.data.result[0].value[1] // "0"' | tr -d '"')
echo "Cost per request: \$$(echo "scale=6; $COST / $REQUESTS" | bc)"
```

### Automated Reporting

```bash
#!/bin/bash
# Daily cost report script
DATE=$(date +%Y-%m-%d)
echo "NeuroNews Daily Cost Report - $DATE"
echo "=================================="

# Total cluster cost
TOTAL_COST=$(curl -s "http://localhost:9003/allocation?window=24h" | jq '[.data[].totalCost] | add')
echo "Total Cluster Cost: \$$TOTAL_COST"

# NeuroNews namespace cost
NEURONEWS_COST=$(curl -s "http://localhost:9003/allocation?window=24h&filter=namespace:neuronews" | jq '.data[].totalCost // 0')
echo "NeuroNews Cost: \$$NEURONEWS_COST"

# Cost breakdown by component
echo ""
echo "Cost by Component:"
curl -s "http://localhost:9003/allocation?window=24h&filter=namespace:neuronews&aggregate=label:app.kubernetes.io/component" | \
  jq -r '.data[] | "\(.name): $\(.totalCost)"' | sort -k2 -nr
```

## DoD Validation

✅ **OpenCost Pod Healthy**: Installation script verifies pod status and readiness  
✅ **Prometheus Metrics**: `node_total_hourly_cost`, `container_cpu_allocation` exposed at `:9003/metrics`  
✅ **API Endpoints**: `/allocation` and `/assets` endpoints accessible and returning data  
✅ **Documentation**: Complete README with curl examples and usage patterns  
✅ **Helm Integration**: Automated installation via Helm with custom values  
✅ **Prometheus Scraping**: Scrape jobs configured for OpenCost metrics collection  

## Security Considerations

### RBAC Configuration

OpenCost requires specific Kubernetes permissions:

```yaml
# Minimal RBAC for OpenCost
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: opencost
rules:
- apiGroups: [""]
  resources: ["nodes", "pods", "services", "namespaces", "persistentvolumes", "persistentvolumeclaims"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets", "daemonsets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["metrics.k8s.io"]
  resources: ["nodes", "pods"]
  verbs: ["get", "list"]
```

### Network Policies

```yaml
# Restrict OpenCost network access
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: opencost-network-policy
  namespace: opencost
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: opencost
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: monitoring
    ports:
    - protocol: TCP
      port: 9003
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: TCP
      port: 443
```

This comprehensive OpenCost integration provides enterprise-grade FinOps capabilities for the NeuroNews platform, enabling detailed cost visibility, optimization opportunities, and automated cost management workflows.
