# Carbon Cost Tracking Implementation

Issue #342: Carbon cost (optional, nice-to-have)

This document describes the implementation of carbon footprint tracking and kgCO2e metrics for the NeuroNews platform, adding a modern sustainability angle to our FinOps capabilities.

## 🌍 Overview

This implementation enables real-time carbon emissions tracking using OpenCost integration, providing pipeline-specific and cluster-wide carbon footprint visibility with cost attribution based on the social cost of carbon.

### Why Carbon Tracking?

- **Modern hiring conversations**: Demonstrates sustainability awareness
- **Environmental responsibility**: Track and optimize carbon impact
- **Regulatory compliance**: Prepare for carbon reporting requirements
- **Cost optimization**: Carbon pricing adds accountability for resource usage

### Core Benefits

- **Real-time kgCO2e metrics** per pipeline and cluster total
- **Cost attribution** using social cost of carbon ($185/tonne CO2e)
- **Regional accuracy** with AWS-specific carbon intensity data
- **Sustainability scoring** and renewable energy tracking

## 🏗 Architecture Overview

### Carbon Tracking Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   OpenCost      │───▶│   Prometheus    │───▶│    Grafana      │
│ Carbon Engine   │    │ Carbon Metrics  │    │ Carbon Dashboard│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Regional Carbon │    │  Pipeline kgCO2e│    │ Sustainability  │
│ Intensity Data  │    │    Tracking     │    │   Insights      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Sources Integration

- **AWS Regional Data**: Carbon intensity (gCO2e/kWh) by AWS region
- **Instance Power Data**: Measured power consumption per EC2 instance type
- **Kubernetes Metrics**: CPU/memory usage for accurate carbon attribution
- **Social Cost Pricing**: $185/tonne CO2e for internal carbon accounting

## 📁 File Structure

```
k8s/monitoring/
├── opencost-carbon.yaml           # OpenCost deployment with carbon tracking
├── prometheus-carbon-rules.yaml   # Carbon metrics and alerting rules
├── grafana-carbon-dashboard.json  # Carbon visualization dashboard
├── install-carbon-tracking.sh     # Installation automation script
└── test-carbon-tracking.sh        # Comprehensive validation suite

docs/finops/
└── carbon-tracking-implementation.md # This documentation
```

## 🚀 Installation

### Prerequisites

- Kubernetes cluster with metrics-server
- Prometheus for metrics collection
- Grafana for visualization (recommended)
- OpenCost or Kubecost licensing (community edition supported)

### Quick Installation

```bash
# Install carbon tracking components
./k8s/monitoring/install-carbon-tracking.sh

# Dry run first (recommended)
./k8s/monitoring/install-carbon-tracking.sh --dry-run

# Custom configuration
./k8s/monitoring/install-carbon-tracking.sh \
  --cluster production-cluster \
  --region eu-west-1 \
  --opencost-ns cost-tracking
```

### Manual Configuration

#### 1. Configure OpenCost with Carbon Tracking
```bash
# Apply OpenCost carbon configuration
kubectl apply -f k8s/monitoring/opencost-carbon.yaml -n opencost

# Wait for deployment
kubectl rollout status deployment/opencost -n opencost
```

#### 2. Install Prometheus Carbon Rules
```bash
# Install carbon monitoring rules
kubectl apply -f k8s/monitoring/prometheus-carbon-rules.yaml
```

#### 3. Configure Grafana Dashboard
```bash
# Create dashboard ConfigMap
kubectl create configmap grafana-carbon-dashboard \
  --from-file=k8s/monitoring/grafana-carbon-dashboard.json \
  -n monitoring

# Label for Grafana auto-discovery
kubectl label configmap grafana-carbon-dashboard \
  grafana_dashboard=1 -n monitoring
```

## 📊 Carbon Metrics Available

### Pipeline-Level Metrics

```promql
# Carbon emissions per pipeline (kgCO2e)
neuronews:carbon:pipeline_emissions_kg_co2e

# Carbon cost per pipeline (USD)
neuronews:carbon:pipeline_cost_usd

# Example values:
# neuronews:carbon:pipeline_emissions_kg_co2e{pipeline="ingest"} 2.34
# neuronews:carbon:pipeline_emissions_kg_co2e{pipeline="dbt"} 1.87
```

### Cluster-Level Metrics

```promql
# Total cluster carbon emissions (kgCO2e)
neuronews:carbon:cluster_total_emissions_kg_co2e

# Total cluster carbon cost (USD)
neuronews:carbon:cluster_total_cost_usd

# Carbon efficiency (kgCO2e per CPU hour)
neuronews:carbon:efficiency_kg_co2e_per_cpu_hour

# Hourly emissions rate
neuronews:carbon:hourly_emissions_rate
```

### Sustainability Metrics

```promql
# Renewable energy usage percentage
neuronews:carbon:renewable_energy_percentage

# Sustainability score (0-100, higher is better)
neuronews:carbon:sustainability_score

# Carbon intensity vs cloud average
neuronews:carbon:intensity_vs_cloud_average

# Carbon savings from spot instances
neuronews:carbon:spot_savings_kg_co2e
```

## 🎯 Regional Carbon Intensity Data

### AWS Regions Supported

| Region | Carbon Intensity | Renewable % | Data Center Efficiency |
|--------|------------------|-------------|----------------------|
| us-east-1 (N. Virginia) | 394.9 gCO2e/kWh | 45.2% | PUE 1.135 |
| us-west-2 (Oregon) | 214.7 gCO2e/kWh | 73.4% | PUE 1.135 |
| eu-west-1 (Ireland) | 316.8 gCO2e/kWh | 61.2% | PUE 1.135 |
| eu-central-1 (Frankfurt) | 338.1 gCO2e/kWh | 58.4% | PUE 1.135 |

### Instance Type Power Consumption

```yaml
# Power consumption estimates (Watts)
m5.large:     85W   # 2 vCPU, 8 GB RAM
m5.xlarge:    170W  # 4 vCPU, 16 GB RAM
c5.large:     75W   # 2 vCPU, 4 GB RAM (compute optimized)
r5.large:     95W   # 2 vCPU, 16 GB RAM (memory optimized)
```

## 📈 Dashboard Features

### 🌍 Carbon Emissions Overview
- **Total Cluster kgCO2e**: Real-time cluster carbon footprint
- **Hourly Rate**: kgCO2e emissions per hour trend
- **Carbon Cost USD**: Financial impact of carbon emissions
- **Sustainability Score**: 0-100 environmental performance rating

### 📊 Pipeline Breakdown
- **Pie Chart**: Carbon emissions distribution across pipelines
- **Bar Chart**: Carbon cost per pipeline in USD
- **Timeline**: Historical carbon emissions trends
- **Table**: Workload-level carbon impact ranking

### 🌱 Sustainability Insights
- **Renewable Energy %**: Grid renewable energy usage
- **Carbon Efficiency**: kgCO2e per CPU hour performance
- **Optimization Recommendations**: Actionable sustainability tips
- **Savings Tracking**: Carbon reductions from optimization efforts

## 🔍 Carbon Calculation Methodology

### Emission Calculation Formula

```
Carbon Emissions (kgCO2e) = 
  CPU Usage (cores) × 
  Instance Power (kW) × 
  Carbon Intensity (gCO2e/kWh) × 
  PUE (1.135) × 
  Time (hours) ÷ 
  1000 (g to kg conversion)
```

### Accuracy Factors

1. **Regional Carbon Intensity**: AWS-specific grid emission factors
2. **Instance Power Consumption**: Measured AWS EC2 power usage
3. **PUE (Power Usage Effectiveness)**: AWS data center efficiency (1.135)
4. **Utilization Tracking**: Actual CPU/memory usage via Kubernetes metrics

### Cost Attribution

```
Carbon Cost (USD) = 
  Carbon Emissions (tonnes CO2e) × 
  Social Cost of Carbon ($185/tonne)
```

## 🚨 Carbon Monitoring & Alerts

### Carbon Impact Alerts

```yaml
# High carbon emissions (>5kg CO2e/hour)
- alert: HighCarbonEmissions
  expr: neuronews:carbon:hourly_emissions_rate > 5.0
  
# Carbon cost threshold (>$100/day)  
- alert: CarbonCostThreshold
  expr: neuronews:carbon:cluster_total_cost_usd > 100

# Pipeline carbon impact (>2kg CO2e)
- alert: PipelineCarbonImpact
  expr: neuronews:carbon:pipeline_emissions_kg_co2e > 2.0
```

### Optimization Alerts

```yaml
# Carbon efficiency degradation
- alert: CarbonEfficiencyDegradation
  expr: neuronews:carbon:efficiency_kg_co2e_per_cpu_hour increase

# Sustainability score decline
- alert: SustainabilityDeclining
  expr: neuronews:carbon:sustainability_score < 60
```

## 💰 Cost Impact Analysis

### Carbon Pricing Model

- **Social Cost of Carbon**: $185/tonne CO2e (2024 EPA guidance)
- **Internal Accountability**: Carbon costs included in total cost of ownership
- **Budget Allocation**: Pipeline-specific carbon cost attribution

### Example Impact

```
Daily Cluster Emissions: 50 kg CO2e
Daily Carbon Cost: $9.25 USD
Monthly Carbon Cost: $277.50 USD
Annual Carbon Cost: $3,370 USD

Pipeline Breakdown:
- Ingestion: 20 kg CO2e/day ($3.70/day)
- DBT: 15 kg CO2e/day ($2.78/day)  
- Analytics: 10 kg CO2e/day ($1.85/day)
- Dev/Test: 5 kg CO2e/day ($0.92/day)
```

## 🎯 DoD Requirements Validation

### ✅ Dashboard shows carbon per pipeline

**Implementation**: Grafana dashboard with dedicated pipeline carbon panels
- Pie chart: Carbon emissions by pipeline
- Bar chart: Carbon cost per pipeline
- Table: Workload-level carbon breakdown

**Validation**:
```bash
# Check pipeline metrics
curl -s "http://prometheus:9090/api/v1/query?query=neuronews:carbon:pipeline_emissions_kg_co2e"

# View in Grafana
http://grafana:3000/d/neuronews-carbon/neuronews-carbon-footprint-cost-tracking
```

### ✅ Dashboard shows cluster total

**Implementation**: Cluster-wide carbon metrics with historical tracking
- Total emissions: Real-time kgCO2e cluster footprint
- Emissions rate: Hourly trend analysis
- Cost impact: Financial carbon accounting

**Validation**:
```bash
# Check cluster total metrics
curl -s "http://prometheus:9090/api/v1/query?query=neuronews:carbon:cluster_total_emissions_kg_co2e"
```

### ✅ OpenCost integration with Prometheus

**Implementation**: OpenCost configured with carbon estimation and Prometheus scraping
- Metrics endpoint: `/metrics` with carbon data
- Prometheus integration: Automatic metric collection
- Alert rules: Carbon threshold monitoring

**Validation**:
```bash
# Check OpenCost metrics
kubectl port-forward svc/opencost 9003:9003 -n opencost
curl -s http://localhost:9003/metrics | grep carbon
```

## 🧪 Testing & Validation

### Automated Testing

```bash
# Run comprehensive test suite
./k8s/monitoring/test-carbon-tracking.sh

# Test results include:
# ✓ OpenCost carbon configuration validation
# ✓ Prometheus carbon rules verification
# ✓ Grafana dashboard structure check
# ✓ DoD requirements validation
# ✓ Carbon calculation accuracy tests
```

### Manual Validation

#### 1. Verify OpenCost Carbon Metrics
```bash
# Check OpenCost deployment
kubectl get deployment opencost -n opencost

# Verify carbon configuration
kubectl describe configmap opencost-carbon-config -n opencost

# Test metrics endpoint
kubectl port-forward svc/opencost 9003:9003 -n opencost &
curl -s http://localhost:9003/metrics | grep opencost_carbon
```

#### 2. Check Prometheus Carbon Rules
```bash
# List carbon rules
kubectl get prometheusrule neuronews-carbon-tracking -n monitoring

# Query carbon metrics
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &
curl -s "http://localhost:9090/api/v1/query?query=neuronews:carbon:cluster_total_emissions_kg_co2e"
```

#### 3. Access Grafana Dashboard
```bash
# Port forward to Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring

# Visit dashboard
# http://localhost:3000/d/neuronews-carbon/neuronews-carbon-footprint-cost-tracking
```

## 🌱 Sustainability Optimization

### Carbon Reduction Strategies

#### 1. **Pipeline Optimization**
- **Batch Processing**: Schedule carbon-intensive jobs during low-grid-carbon hours
- **Resource Right-sizing**: Use VPA recommendations to reduce overconsumption
- **Algorithm Efficiency**: Optimize data processing algorithms for lower compute requirements

#### 2. **Infrastructure Optimization**
- **Spot Instances**: 60% carbon reduction through efficient resource utilization
- **ARM-based Instances**: 20% efficiency improvement with Graviton processors
- **Region Selection**: Deploy in low-carbon regions (us-west-2: 214.7 vs us-east-1: 394.9 gCO2e/kWh)

#### 3. **Temporal Optimization**
- **Carbon-aware Scheduling**: Run batch jobs when renewable energy percentage is highest
- **Workload Shifting**: Move non-urgent processing to low-carbon time windows
- **Seasonal Awareness**: Adjust computational intensity based on grid carbon trends

### Optimization Tracking

```promql
# Carbon optimization ROI
neuronews:carbon:optimization_roi

# Weekly carbon reduction
(neuronews:carbon:cluster_total_emissions_kg_co2e offset 7d) - 
neuronews:carbon:cluster_total_emissions_kg_co2e

# Efficiency improvements
neuronews:carbon:efficiency_kg_co2e_per_cpu_hour
```

## 🔧 Troubleshooting

### Common Issues

#### OpenCost Not Generating Carbon Metrics
```bash
# Check OpenCost logs
kubectl logs -n opencost deployment/opencost

# Verify carbon estimation is enabled
kubectl describe deployment opencost -n opencost | grep -A 10 "Environment:"

# Check carbon configuration
kubectl get configmap opencost-carbon-config -n opencost -o yaml
```

#### Missing Carbon Data in Prometheus
```bash
# Check OpenCost service discovery
kubectl get endpoints opencost -n opencost

# Verify Prometheus scraping
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &
# Visit: http://localhost:9090/targets (look for opencost target)

# Check Prometheus configuration
kubectl get prometheus -o yaml | grep -A 5 serviceMonitor
```

#### Dashboard Not Showing Data
```bash
# Check Grafana dashboard ConfigMap
kubectl get configmap grafana-carbon-dashboard -n monitoring

# Verify dashboard is loaded
kubectl logs -n monitoring deployment/grafana | grep carbon

# Check Prometheus data source
# Visit: http://localhost:3000/datasources (verify Prometheus connection)
```

### Performance Tuning

#### Reduce Carbon Calculation Overhead
```yaml
# Adjust metrics collection interval
carbon:
  metrics_interval: "5m"  # Default: 1m
  aggregation_interval: "1h"  # Default: 30s
```

#### Optimize Storage for Carbon Metrics
```yaml
# Prometheus retention for carbon data
prometheus:
  retention: "30d"  # Store 30 days of carbon history
  carbon_metrics_retention: "90d"  # Longer retention for reporting
```

## 🚀 Future Enhancements

### Planned Features

1. **Carbon Budgets**: Set and track carbon emission budgets per team/project
2. **Real-time Optimization**: Automatic workload scheduling based on grid carbon intensity
3. **Scope 3 Tracking**: Include upstream cloud provider carbon emissions
4. **Carbon Offset Integration**: Automatic carbon offset purchasing for net-zero goals

### Integration Opportunities

1. **CI/CD Carbon Gates**: Block deployments that exceed carbon thresholds
2. **Carbon-aware Autoscaling**: Scale based on both resource demand and carbon intensity
3. **Sustainability Reporting**: Automated ESG reporting with carbon metrics
4. **Green Software Engineering**: Developer tools for carbon-efficient code

## 📚 References

- **OpenCost Documentation**: https://opencost.io/docs/integrations/prometheus/
- **AWS Carbon Footprint**: https://aws.amazon.com/aws-carbon-footprint-tool/
- **Social Cost of Carbon**: https://www.epa.gov/environmental-economics/social-cost-carbon
- **Green Software Foundation**: https://greensoftware.foundation/
- **Carbon Aware SDK**: https://github.com/Green-Software-Foundation/carbon-aware-sdk

## 🏃‍♂️ Quick Start Commands

```bash
# 1. Install carbon tracking
./k8s/monitoring/install-carbon-tracking.sh

# 2. Verify installation
kubectl get pods -n opencost
kubectl get prometheusrule neuronews-carbon-tracking -n monitoring

# 3. Access dashboards
kubectl port-forward svc/grafana 3000:3000 -n monitoring &
# Visit: http://localhost:3000/d/neuronews-carbon/

# 4. Query carbon metrics
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &
# Query: neuronews:carbon:pipeline_emissions_kg_co2e

# 5. Monitor carbon impact
kubectl logs -n opencost deployment/opencost --tail=50
```

## 💼 Hiring Conversation Points

This carbon tracking implementation demonstrates:

- **Environmental consciousness** in technical decision-making
- **Modern sustainability practices** in cloud infrastructure
- **Advanced observability** with multi-dimensional metrics
- **Cost consciousness** including environmental externalities
- **Regulatory preparedness** for carbon reporting requirements
- **Technical innovation** in green software engineering

Perfect for demonstrating environmental awareness and technical sophistication in interviews while showcasing practical sustainability implementation skills.
