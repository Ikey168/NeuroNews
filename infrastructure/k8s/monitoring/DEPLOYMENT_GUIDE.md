# NGINX Performance Monitoring Deployment Guide

## Overview
This guide provides comprehensive NGINX performance monitoring for the NeuroNews API with Prometheus metrics collection, Grafana dashboards, and structured logging.

## Architecture
```
API Requests → NGINX → Application
     ↓
Prometheus Exporter → Prometheus → Grafana
     ↓
Fluentd → Structured Logs → Analysis
```

## Components

### 1. NGINX with Performance Monitoring
- **Configuration**: Enhanced NGINX config with prometheus metrics endpoint
- **Logging**: Multi-format logging (main, JSON, performance metrics)
- **Metrics**: Request rates, response times, error rates, connection counts
- **Health Checks**: Upstream server monitoring and circuit breaker patterns

### 2. Prometheus Metrics Collection
- **Target**: NGINX stub_status and prometheus exporter
- **Retention**: 15 days of metrics data
- **Alerting**: Comprehensive rules for availability, performance, and errors
- **Scraping**: Every 15 seconds for real-time monitoring

### 3. Grafana Dashboard
- **Panels**: Request rate, error rate, response time percentiles, bandwidth
- **Alerts**: Integrated alerting for critical performance thresholds
- **Time Range**: Real-time with historical analysis capabilities

### 4. Fluentd Log Aggregation
- **Parsing**: Access logs, error logs, performance logs
- **Format**: Structured JSON with Kubernetes metadata
- **Enrichment**: Request tracing, geographic analysis, user agent parsing

## Deployment Steps

### Prerequisites
```bash
# Ensure Kubernetes cluster is running
kubectl cluster-info

# Create namespace
kubectl create namespace neuronews

# Apply RBAC permissions
kubectl apply -f k8s/monitoring/prometheus-deployment.yaml
```

### 1. Deploy Configuration
```bash
# Apply NGINX configuration
kubectl apply -f k8s/nginx/monitoring-configmap.yaml

# Apply Fluentd configuration
kubectl apply -f k8s/nginx/fluentd-config.yaml

# Apply Prometheus configuration
kubectl apply -f k8s/monitoring/prometheus-nginx-config.yaml
```

### 2. Deploy Monitoring Stack
```bash
# Deploy Prometheus
kubectl apply -f k8s/monitoring/prometheus-deployment.yaml

# Deploy NGINX with monitoring
kubectl apply -f k8s/nginx/monitoring-deployment.yaml
kubectl apply -f k8s/nginx/monitoring-service.yaml

# Deploy Grafana dashboard (if Grafana is available)
kubectl apply -f k8s/monitoring/grafana-nginx-dashboard.yaml
```

### 3. Verify Deployment
```bash
# Check all pods are running
kubectl get pods -n neuronews

# Check services
kubectl get svc -n neuronews

# Check configmaps
kubectl get configmap -n neuronews

# Check logs
kubectl logs -n neuronews deployment/nginx-monitoring -c nginx
kubectl logs -n neuronews deployment/nginx-monitoring -c prometheus-exporter
kubectl logs -n neuronews deployment/nginx-monitoring -c fluentd
```

## Testing the Monitoring

### 1. Generate Test Traffic
```bash
# Get NGINX service URL
NGINX_URL=$(kubectl get svc nginx-monitoring-loadbalancer -n neuronews -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Generate load
for i in {1..1000}; do
  curl -s http://$NGINX_URL/api/v1/news > /dev/null &
  curl -s http://$NGINX_URL/api/v1/analytics > /dev/null &
  if (( $i % 100 == 0 )); then
    echo "Sent $i requests"
    sleep 1
  fi
done
wait
```

### 2. Access Monitoring Interfaces
```bash
# Port forward to Prometheus
kubectl port-forward -n neuronews svc/prometheus-nginx-service 9090:9090 &
echo "Prometheus available at: http://localhost:9090"

# Port forward to NGINX metrics
kubectl port-forward -n neuronews svc/nginx-monitoring-service 9113:9113 &
echo "NGINX metrics available at: http://localhost:9113/metrics"

# Port forward to NGINX
kubectl port-forward -n neuronews svc/nginx-monitoring-loadbalancer 8080:80 &
echo "NGINX available at: http://localhost:8080"
```

### 3. Verify Metrics Collection
```bash
# Check NGINX metrics endpoint
curl http://localhost:9113/metrics | grep nginx_

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="nginx-monitoring")'

# Check if metrics are being collected
curl -s "http://localhost:9090/api/v1/query?query=nginx_http_requests_total" | jq '.data.result'
```

## Performance Metrics

### Key Metrics Collected
- **nginx_http_requests_total**: Total HTTP requests by status code
- **nginx_http_request_duration_seconds**: Request duration histogram
- **nginx_connections_active**: Active client connections
- **nginx_connections_reading**: Reading client connections
- **nginx_connections_writing**: Writing client connections
- **nginx_connections_waiting**: Waiting client connections

### Alerting Rules
- **High Error Rate**: >5% error rate for 5 minutes
- **High Response Time**: P95 response time >1s for 5 minutes
- **Service Down**: NGINX unavailable for 1 minute
- **High Connection Count**: >1000 active connections

## Grafana Dashboard Features

### Request Monitoring
- Requests per second over time
- Request distribution by endpoint
- Status code breakdown
- Geographic request distribution

### Performance Analysis
- Response time percentiles (P50, P95, P99)
- Request duration histograms
- Bandwidth utilization
- Connection pool metrics

### Error Analysis
- Error rate trends
- Error breakdown by type
- Failed request patterns
- Upstream server health

### Capacity Planning
- Connection usage trends
- Request volume patterns
- Resource utilization
- Performance bottleneck identification

## Troubleshooting

### Common Issues
1. **Metrics not appearing**: Check prometheus exporter sidecar logs
2. **High memory usage**: Adjust retention period or sampling
3. **Connection refused**: Verify service discovery and networking
4. **Missing logs**: Check Fluentd configuration and parsing rules

### Debug Commands
```bash
# Check NGINX configuration
kubectl exec -n neuronews deployment/nginx-monitoring -c nginx -- nginx -t

# Check Prometheus configuration
kubectl exec -n neuronews deployment/prometheus-nginx -- promtool check config /etc/prometheus/prometheus.yml

# Check Fluentd logs
kubectl logs -n neuronews deployment/nginx-monitoring -c fluentd -f

# Check metrics endpoint
kubectl exec -n neuronews deployment/nginx-monitoring -c nginx -- curl localhost:8080/nginx_status
```

## Performance Optimization

### For High Traffic
- Increase NGINX worker processes
- Adjust Prometheus scraping interval
- Implement log sampling
- Use persistent volumes for Prometheus storage

### For Resource Constraints
- Reduce metrics retention period
- Limit log verbosity
- Implement metric filtering
- Use resource limits and requests

## Security Considerations
- Metrics endpoints are internal only
- Log data contains no sensitive information
- RBAC permissions are minimal required
- TLS encryption for production deployments

## Maintenance
- Regular log rotation and cleanup
- Prometheus storage management
- Dashboard and alert rule updates
- Performance baseline reviews
