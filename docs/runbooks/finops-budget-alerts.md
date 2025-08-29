# FinOps Budget Alerts Runbook

Issue #338: Budget & burn-rate alerts (monthly projection + drift)

This runbook provides guidance for responding to FinOps budget and cost drift alerts.

## 🚨 Alert Overview

### Critical Alerts
- **FinOpsMonthlyBudgetCriticalBreach**: Monthly projection >150% of budget
- **FinOpsCostDriftCritical**: Infrastructure costs doubled week-over-week

### Warning Alerts
- **FinOpsMonthlyBudgetBreach**: Monthly projection exceeds budget
- **FinOpsCostDriftWoW**: ≥30% cost increase week-over-week
- **FinOpsDailyBudgetBurnRate**: Daily spend exceeds allocation
- **FinOpsUnitEconomicsArticles**: Cost per 1k articles above threshold
- **FinOpsUnitEconomicsRAGQueries**: Cost per RAG query above threshold
- **FinOpsLowResourceEfficiency**: Poor cost per business outcome

## 🔍 Investigation Steps

### 1. Immediate Assessment
```bash
# Check current costs
kubectl port-forward service/grafana 3000:80 -n monitoring
# Open: http://localhost:3000/d/unit-economics-001/

# Check Prometheus alerts
kubectl port-forward service/prometheus-server 9090:80 -n monitoring
# Open: http://localhost:9090/alerts
```

### 2. Cost Analysis
```bash
# Query current hourly cost
curl -s "http://localhost:9090/api/v1/query?query=sum(opencost_node_cost_hourly)"

# Query monthly projection
curl -s "http://localhost:9090/api/v1/query?query=sum(opencost_node_cost_hourly)*24*30"

# Check cost breakdown by namespace
curl -s "http://localhost:9090/api/v1/query?query=sum(opencost_node_cost_hourly)by(namespace)"
```

### 3. Resource Investigation
```bash
# Check top resource consumers
kubectl top nodes
kubectl top pods --all-namespaces --sort-by=memory
kubectl top pods --all-namespaces --sort-by=cpu

# Check recent deployments
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | head -20

# Check scaling events
kubectl get hpa --all-namespaces
kubectl describe hpa <hpa-name> -n <namespace>
```

## 🛠 Resolution Strategies

### Budget Breach Response

#### Immediate Actions (Critical)
1. **Identify cost drivers**:
   ```bash
   # Check cost by workload
   kubectl get pods --all-namespaces -o wide
   kubectl describe nodes | grep -A5 "Allocated resources"
   ```

2. **Scale down non-critical workloads**:
   ```bash
   # Scale down development environments
   kubectl scale deployment <dev-deployment> --replicas=0 -n dev
   
   # Reduce staging replicas
   kubectl scale deployment <staging-deployment> --replicas=1 -n staging
   ```

3. **Check for runaway processes**:
   ```bash
   # Look for high CPU/memory pods
   kubectl top pods --all-namespaces --sort-by=cpu | head -10
   kubectl top pods --all-namespaces --sort-by=memory | head -10
   ```

#### Medium-term Actions
1. **Right-size resources**:
   ```bash
   # Check resource requests vs actual usage
   kubectl describe pod <pod-name> -n <namespace>
   ```

2. **Implement resource limits**:
   ```yaml
   resources:
     requests:
       memory: "256Mi"
       cpu: "250m"
     limits:
       memory: "512Mi"
       cpu: "500m"
   ```

3. **Enable cluster autoscaling**:
   ```bash
   # Check autoscaler status
   kubectl get nodes -o wide
   kubectl describe configmap cluster-autoscaler-status -n kube-system
   ```

### Cost Drift Response

#### Week-over-Week Analysis
1. **Compare time periods**:
   ```bash
   # This week vs last week cost
   curl -s "http://localhost:9090/api/v1/query?query=sum_over_time(opencost_node_cost_hourly[7d])"
   curl -s "http://localhost:9090/api/v1/query?query=sum_over_time(opencost_node_cost_hourly%20offset%207d[7d])"
   ```

2. **Check for new deployments**:
   ```bash
   # Deployments created in last 7 days
   kubectl get deployments --all-namespaces \
     -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,CREATED:.metadata.creationTimestamp \
     | awk -v date="$(date -d '7 days ago' '+%Y-%m-%d')" '$3 > date'
   ```

3. **Analyze scaling events**:
   ```bash
   # HPA scaling history
   kubectl get events --all-namespaces --field-selector reason=SuccessfulRescale
   ```

### Unit Economics Optimization

#### Articles Cost Optimization
1. **Analyze ingestion pipeline**:
   ```bash
   # Check articles ingested rate
   curl -s "http://localhost:9090/api/v1/query?query=rate(neuro_articles_ingested_total[1h])*3600"
   
   # Check processing efficiency
   kubectl top pods -n data-pipeline --sort-by=cpu
   ```

2. **Optimize batch processing**:
   - Review Spark job configurations
   - Adjust batch sizes and parallelism
   - Consider spot instances for batch workloads

#### RAG Query Cost Optimization
1. **Analyze query patterns**:
   ```bash
   # Check RAG query rate
   curl -s "http://localhost:9090/api/v1/query?query=rate(neuro_rag_queries_total[1h])*3600"
   
   # Check API response times
   curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))"
   ```

2. **Implement caching**:
   - Enable query result caching
   - Implement embedding caching
   - Use CDN for static content

3. **Optimize inference**:
   - Batch similar queries
   - Use smaller models for simple queries
   - Implement request deduplication

## 📊 Monitoring Queries

### Cost Monitoring
```promql
# Current hourly cost
sum(opencost_node_cost_hourly)

# Monthly projection
sum(opencost_node_cost_hourly) * 24 * 30

# Daily cost
sum_over_time(opencost_node_cost_hourly[24h])

# Week-over-week change
(sum_over_time(opencost_node_cost_hourly[7d]) - sum_over_time(opencost_node_cost_hourly offset 7d [7d])) / sum_over_time(opencost_node_cost_hourly offset 7d [7d])

# Cost by namespace
sum(opencost_node_cost_hourly) by (namespace)
```

### Business Metrics
```promql
# Articles per hour
rate(neuro_articles_ingested_total[1h]) * 3600

# RAG queries per hour
rate(neuro_rag_queries_total[1h]) * 3600

# Cost per 1k articles
cost:cluster_hourly:sum / (articles:rate_1h / 1000)

# Cost per RAG query
cost:cluster_hourly:sum / ragq:rate_1h
```

### Efficiency Metrics
```promql
# Articles per euro
articles:rate_1h / cost:cluster_hourly:sum

# Queries per euro
ragq:rate_1h / cost:cluster_hourly:sum

# CPU efficiency
avg(rate(container_cpu_usage_seconds_total[5m])) / avg(kube_pod_container_resource_requests{resource="cpu"})

# Memory efficiency
avg(container_memory_working_set_bytes) / avg(kube_pod_container_resource_requests{resource="memory"})
```

## 🔧 Configuration Updates

### Threshold Adjustment
```bash
# Update budget threshold
BUDGET_EUR=10000 ./install-finops-budget-alerts.sh

# Update unit economics thresholds
COST_PER_1K_ARTICLES_THRESHOLD=3.0 \
COST_PER_RAG_QUERY_THRESHOLD=0.1 \
./install-finops-budget-alerts.sh
```

### Notification Configuration
```bash
# Configure Slack notifications
export SLACK_WEBHOOK_URL_FINOPS="https://hooks.slack.com/services/..."

# Configure email notifications
export FINOPS_EMAIL_CRITICAL="platform-team@company.com"

# Apply configuration
./install-finops-budget-alerts.sh
```

## 📞 Escalation Paths

### Severity Levels

#### Critical (Response: Immediate)
- Monthly projection >150% budget
- Infrastructure costs doubled
- Business-critical services affected

**Actions:**
1. Page on-call engineer
2. Scale down non-critical services
3. Notify finance team
4. Create incident ticket

#### Warning (Response: 1-4 hours)
- Monthly projection exceeds budget
- 30%+ cost increase
- Unit economics thresholds exceeded

**Actions:**
1. Investigate cost drivers
2. Implement optimization measures
3. Update forecasts
4. Schedule optimization review

#### Info (Response: Next business day)
- Efficiency alerts
- Trend notifications
- Optimization opportunities

**Actions:**
1. Add to optimization backlog
2. Schedule review meeting
3. Update monitoring thresholds

## 📋 Prevention Strategies

### Proactive Monitoring
1. **Set up regular cost reviews**:
   - Weekly cost trending meetings
   - Monthly budget variance analysis
   - Quarterly optimization planning

2. **Implement cost controls**:
   - Resource quotas per namespace
   - Pod disruption budgets
   - Cluster autoscaler limits

3. **Automate responses**:
   - Auto-scaling policies
   - Cost-based alerts
   - Automatic resource cleanup

### Best Practices
1. **Resource Management**:
   - Set appropriate requests and limits
   - Use priority classes
   - Implement pod disruption budgets

2. **Environment Management**:
   - Scale down dev/test environments after hours
   - Use spot instances for batch workloads
   - Implement resource lifecycle policies

3. **Monitoring**:
   - Regular dashboard reviews
   - Automated anomaly detection
   - Trend analysis and forecasting

## 🔗 Related Documentation

- [NeuroNews FinOps Dashboard](http://grafana:3000/d/neuronews-finops/)
- [Unit Economics Dashboard](http://grafana:3000/d/unit-economics-001/)
- [OpenCost Documentation](https://opencost.io/docs/)
- [Prometheus Alerting](https://prometheus.io/docs/alerting/latest/overview/)
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

## 📞 Contact Information

- **On-call Engineer**: #on-call-platform
- **FinOps Team**: #finops-team
- **Platform Team**: #platform-team
- **Finance Team**: finance@company.com
- **Incident Management**: #incidents
