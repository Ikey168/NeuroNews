# NeuroNews Grafana FinOps Dashboards

Comprehensive cost visualization dashboards for Kubernetes FinOps including OpenCost integration and pipeline-specific cost allocation.

## 🎯 Overview

This collection provides two production-ready Grafana dashboards:

1. **OpenCost Overview** - General cluster cost monitoring and resource efficiency
2. **NeuroNews FinOps** - Business-specific cost allocation by pipeline, team, and environment

## 📊 Dashboard Features

### OpenCost Overview Dashboard

- **Total Cluster Cost**: Monthly cost calculation from node pricing
- **Cost Breakdown**: Compute, storage, and network cost distribution
- **Namespace Costs**: Cost allocation by Kubernetes namespace
- **Top Workloads**: Most expensive pods and deployments
- **Resource Efficiency**: CPU and memory utilization vs. requests

### NeuroNews FinOps Dashboard

- **Monthly Cluster Cost**: Executive summary with cost thresholds
- **Pipeline Cost Allocation**: Cost by business function (ingest, transform, api, rag, monitoring, infra)
- **Team Cost Allocation**: Cost attribution by owning team
- **Environment Costs**: Development lifecycle cost tracking (dev, staging, prod)
- **Cost Center Allocation**: Business unit cost attribution
- **Load Balancer Costs**: Network service cost tracking
- **Storage Costs**: Persistent volume cost allocation
- **Resource Efficiency**: Utilization metrics by pipeline

## 🚀 Quick Start

### Prerequisites

- Kubernetes cluster with Grafana installed
- OpenCost deployed and collecting metrics
- Prometheus scraping OpenCost metrics
- Workloads labeled with FinOps schema (see [FinOps Labeling](../docs/finops/labels.md))

### Installation

```bash
# Install dashboards
cd grafana
./install.sh

# Validate installation
./install.sh validate

# Access Grafana (if using port-forward)
kubectl port-forward svc/grafana -n monitoring 3000:80
```

Then visit http://localhost:3000 and navigate to:
- **OpenCost** folder → OpenCost Overview
- **FinOps** folder → NeuroNews FinOps

## 📁 File Structure

```
grafana/
├── install.sh                           # Installation script
├── dashboards/
│   ├── opencost-overview.json          # OpenCost overview dashboard
│   └── neuronews-finops.json           # NeuroNews FinOps dashboard
├── provisioning/
│   ├── dashboards/
│   │   └── finops.yaml                 # Dashboard provisioning config
│   └── datasources/
│       └── prometheus.yaml             # OpenCost datasource config
├── k8s-manifests.yaml                  # Kubernetes ConfigMaps
└── README.md                           # This file
```

## 🔧 Configuration

### Required Labels

The NeuroNews FinOps dashboard requires workloads to have these labels:

```yaml
metadata:
  labels:
    app: "my-app"              # Application name
    component: "backend"       # Component type
    pipeline: "api"            # Business pipeline
    team: "neuronews"          # Owning team
    env: "prod"                # Environment
    cost_center: "product"     # Cost center
```

### Prometheus Queries

The dashboards use these key PromQL patterns:

#### Monthly Cluster Cost
```promql
sum(opencost_node_cost_hourly) * 730
```

#### Cost by Pipeline
```promql
sum by (pipeline) (
  (avg(kube_pod_container_resource_requests{resource="cpu"}) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="compute"}))
  +
  ((avg(kube_pod_container_resource_requests{resource="memory"})/(1024^3)) * on(node) group_left() avg(opencost_node_cost_hourly{cost_type="memory"}))
) * on(pod) group_right() kube_pod_labels{label_pipeline!=""}
```

#### Load Balancer Costs
```promql
sum(opencost_load_balancer_cost) by (namespace)
```

#### Storage Costs
```promql
sum by (namespace) (kube_persistentvolume_capacity_bytes * on(persistentvolume) group_left() opencost_pv_cost_hourly) / 1024^3
```

## 🎛 Dashboard Variables

### NeuroNews FinOps Dashboard

- **Pipeline**: Filter by business function (ingest, transform, dbt, api, rag, monitoring, infra)
- **Environment**: Filter by environment (dev, staging, prod, test)
- **Prometheus Datasource**: Select Prometheus instance

## 📈 Metrics and Alerts

### Key Cost Metrics

| Metric | Description | Threshold |
|--------|-------------|-----------|
| Monthly Cluster Cost | Total infrastructure spend | > $1000 (red) |
| Pipeline Cost Ratio | Cost distribution balance | Monitor for skew |
| Resource Efficiency | CPU/Memory utilization | < 80% (waste alert) |
| Storage Cost Growth | PV cost trend | > 20% month-over-month |

### Recommended Alerts

```yaml
# High cluster cost alert
- alert: HighClusterCost
  expr: sum(opencost_node_cost_hourly) * 730 > 1000
  labels:
    severity: warning
  annotations:
    summary: "Monthly cluster cost exceeds $1000"

# Low resource efficiency
- alert: LowResourceEfficiency
  expr: avg(rate(container_cpu_usage_seconds_total[5m]) / on(pod) group_left() kube_pod_container_resource_requests{resource="cpu"}) < 0.3
  labels:
    severity: info
  annotations:
    summary: "Low CPU efficiency detected"
```

## 🔗 Integration Points

### OpenCost API

The dashboards integrate with OpenCost's Prometheus metrics:

```bash
# Test OpenCost connectivity
curl http://opencost.opencost.svc.cluster.local:9003/metrics

# Query allocation API
curl "http://opencost.opencost.svc.cluster.local:9003/allocation?window=7d&aggregate=label:pipeline"
```

### Grafana Provisioning

Dashboards are automatically imported via Grafana provisioning:

```yaml
# grafana/provisioning/dashboards/finops.yaml
providers:
  - name: "NeuroNews FinOps Dashboards"
    folder: "FinOps"
    options:
      path: /var/lib/grafana/dashboards/finops
```

## 🛠 Troubleshooting

### Common Issues

**No Data in Dashboards**:
```bash
# Check OpenCost is running
kubectl get pods -n opencost

# Verify Prometheus is scraping OpenCost
kubectl logs -n monitoring prometheus-server-xxx | grep opencost

# Check FinOps labels on workloads
kubectl get pods --show-labels | grep pipeline
```

**Missing Cost Allocation**:
```bash
# Verify workloads have required labels
kubectl get deployments -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.pipeline}{"\n"}{end}'

# Check OpenCost metrics
curl http://opencost:9003/metrics | grep allocation
```

**Dashboard Import Errors**:
```bash
# Check ConfigMaps
kubectl get configmap grafana-dashboards-finops -n monitoring

# Verify Grafana provisioning
kubectl logs -n monitoring grafana-xxx | grep provisioning

# Manual dashboard import via Grafana UI
```

### Debug Commands

```bash
# View dashboard ConfigMap
kubectl describe configmap grafana-dashboards-finops -n monitoring

# Check Grafana logs
kubectl logs -n monitoring deployment/grafana

# Test Prometheus queries
kubectl port-forward -n monitoring svc/prometheus-server 9090:80
# Visit http://localhost:9090 and test queries

# Validate OpenCost metrics
kubectl port-forward -n opencost svc/opencost 9003:9003
curl http://localhost:9003/metrics
```

## 📋 Manual Installation

If automatic installation fails:

1. **Apply ConfigMaps**:
   ```bash
   kubectl apply -f k8s-manifests.yaml
   ```

2. **Mount in Grafana Deployment**:
   ```yaml
   spec:
     template:
       spec:
         containers:
         - name: grafana
           volumeMounts:
           - name: dashboards-finops
             mountPath: /var/lib/grafana/dashboards/finops
         volumes:
         - name: dashboards-finops
           configMap:
             name: grafana-dashboards-finops
   ```

3. **Restart Grafana**:
   ```bash
   kubectl rollout restart deployment/grafana -n monitoring
   ```

## 🎨 Customization

### Adding New Panels

1. Edit dashboard JSON files in `dashboards/`
2. Update the ConfigMap:
   ```bash
   kubectl create configmap grafana-dashboards-finops \
     --from-file=dashboards/ \
     --namespace=monitoring \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
3. Restart Grafana to reload

### Custom Cost Dimensions

Add new cost allocation dimensions by:

1. Adding labels to workloads
2. Creating new panel queries:
   ```promql
   sum by (custom_label) (
     opencost_allocation_cpu_cost + opencost_allocation_memory_cost
   ) * on(pod) group_right() kube_pod_labels{label_custom_label!=""}
   ```

### Theme and Styling

Dashboards support both light and dark themes:
- Default: Dark theme
- Light theme: Change in Grafana preferences

## 📊 Sample Queries

### Executive Summary
```promql
# Total monthly cost
sum(opencost_node_cost_hourly) * 730

# Cost per team
sum by (team) (opencost_allocation_total_cost) * on(pod) group_right() kube_pod_labels{label_team!=""}

# Most expensive namespaces
topk(5, sum by (namespace) (opencost_allocation_total_cost))
```

### Efficiency Analysis
```promql
# CPU efficiency by pipeline
avg by (pipeline) (
  rate(container_cpu_usage_seconds_total[5m]) / 
  on(pod) group_left() kube_pod_container_resource_requests{resource="cpu"}
) * on(pod) group_right() kube_pod_labels{label_pipeline!=""}

# Memory waste by team
sum by (team) (
  kube_pod_container_resource_requests{resource="memory"} - 
  container_memory_working_set_bytes
) * on(pod) group_right() kube_pod_labels{label_team!=""}
```

## 🔄 Maintenance

### Regular Tasks

**Weekly**:
- Review cost trends and anomalies
- Validate dashboard data accuracy
- Check for unlabeled workloads

**Monthly**:
- Update cost thresholds based on budget
- Review team and pipeline allocations
- Optimize resource requests based on efficiency data

### Dashboard Updates

To update dashboards:

1. Edit JSON files locally
2. Test in development Grafana instance
3. Update ConfigMaps in production
4. Restart Grafana to reload

## 📞 Support

For dashboard issues:

1. Check the troubleshooting section above
2. Validate OpenCost and Prometheus connectivity
3. Verify FinOps labeling on workloads
4. Review Grafana logs for import errors

## 🔗 Related Documentation

- [FinOps Labeling Governance](../docs/finops/labels.md)
- [OpenCost Integration](../docs/finops/opencost.md)
- [Monitoring Setup](../docs/monitoring/overview.md)
- [Kubernetes Cost Optimization](../docs/finops/cost-optimization.md)

---

**Version**: 1.0  
**Compatible with**: Grafana 8.0+, OpenCost 1.0+  
**Last Updated**: 2024-01-01  
**Maintainer**: Platform Team
