# NGINX Rate Limiting & DDoS Protection Implementation Guide

## Overview
This guide provides comprehensive NGINX rate limiting and DDoS protection for the NeuroNews API, addressing Issue #86 with multi-layered security measures including rate limiting, bot detection, fail2ban integration, and geo-blocking capabilities.

## Architecture
```
Internet Traffic → NGINX (Rate Limiting + DDoS Protection) → Application
     ↓
Fail2ban (IP Banning) → iptables (Firewall Rules)
     ↓
Fluentd (Security Logging) → Centralized Logging → Analysis
     ↓
Prometheus (Security Metrics) → Grafana (Security Dashboard)
```

## Security Components

### 1. NGINX Rate Limiting
- **API Rate Limiting**: 100 requests per minute per IP address
- **Burst Protection**: 10 requests per second with controlled burst handling
- **Authentication Endpoints**: Strict 5 requests per minute for login/auth
- **Search Endpoints**: 20 requests per minute for search operations
- **Download/Upload**: 1 request per second for file operations
- **User-based Limits**: 200 requests per minute for authenticated users

### 2. Bot Detection and Blocking
- **User Agent Analysis**: Detects and blocks known bot patterns
- **Request Pattern Analysis**: Identifies suspicious request paths
- **Empty User Agent Blocking**: Blocks requests without user agents
- **Script Detection**: Identifies automated tools (curl, wget, python)
- **Honeypot Paths**: Blocks access to common attack vectors

### 3. Fail2ban Integration
- **HTTP Authentication Failures**: Bans IPs with repeated auth failures
- **Rate Limit Violations**: Automatic banning for rate limit abuse
- **Script Kiddie Protection**: Blocks common exploit attempts
- **Bad Bot Banning**: Identifies and bans malicious crawlers
- **DDoS Pattern Recognition**: Detects and mitigates DDoS attacks

### 4. Geo-blocking
- **GeoIP2 Database**: Real-time country identification
- **Configurable Blocking**: Block traffic from specific countries
- **Security Headers**: Enhanced security headers for all responses
- **IP Reputation**: Integration with threat intelligence feeds

### 5. Security Logging and Monitoring
- **Structured Logging**: JSON-formatted security events
- **Real-time Analysis**: Immediate threat detection and response
- **Metrics Collection**: Prometheus integration for monitoring
- **Event Correlation**: Advanced threat pattern recognition

## Deployment Architecture

### Kubernetes Components
```yaml
- nginx-ddos-protection (Deployment)
  ├── nginx (Main container with rate limiting)
  ├── prometheus-exporter (Metrics collection)
  ├── fail2ban (DDoS protection and IP banning)
  └── fluentd (Security event logging)
- nginx-ddos-protection-service (ClusterIP)
- nginx-ddos-protection-loadbalancer (LoadBalancer)
- nginx-ddos-protection-headless (Headless service)
- Network Policies (Additional security layer)
```

## Rate Limiting Configuration

### Rate Limiting Zones
```nginx
# General API rate limiting: 100 requests per minute per IP
limit_req_zone $binary_remote_addr zone=api_limit:50m rate=100r/m;

# Burst API rate limiting: 10 requests per second per IP
limit_req_zone $binary_remote_addr zone=api_burst:50m rate=10r/s;

# Authentication endpoints: 5 requests per minute per IP
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/m;

# Search endpoints: 20 requests per minute per IP
limit_req_zone $binary_remote_addr zone=search_limit:10m rate=20r/m;

# Download/upload endpoints: 1 request per second per IP
limit_req_zone $binary_remote_addr zone=download_limit:10m rate=1r/s;

# User-based rate limiting for authenticated users
limit_req_zone $http_x_user_id zone=user_api_limit:10m rate=200r/m;
```

### Endpoint-Specific Protection
- **Authentication Endpoints** (`/api/v1/auth/*`): Strict 5 req/min limit
- **Search Endpoints** (`/api/v1/search/*`): Moderate 20 req/min limit
- **File Operations** (`/api/v1/download/*`): Conservative 1 req/sec limit
- **General API** (`/api/v1/*`): Standard 100 req/min limit
- **Static Content**: Light rate limiting with caching headers

## DDoS Protection Features

### Connection Limiting
- **Per-IP Connections**: Maximum 20 concurrent connections per IP
- **Per-Server Connections**: Maximum 1000 total server connections
- **Connection Timeouts**: Aggressive timeouts for slow connections
- **Request Size Limits**: Maximum 10MB request size

### Attack Pattern Detection
```nginx
# Detect rapid consecutive requests
map $remote_addr $request_rate {
    default "";
    ~. $binary_remote_addr;
}

# Block suspicious query strings
if ($query_string ~* "(GLOBALS|_REQUEST|_SESSION|_COOKIE|_SERVER)") {
    return 403 "Malicious query string";
}

# Block overly long query strings (DDoS amplification)
if ($query_string ~ ".{1000,}") {
    return 413 "Query string too long";
}
```

### Security Headers
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'" always;
```

## Fail2ban Configuration

### Jail Configuration
```ini
[nginx-limit-req]
enabled = true
filter = nginx-limit-req
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 3600
findtime = 600

[nginx-ddos]
enabled = true
filter = nginx-ddos
logpath = /var/log/nginx/access.log
maxretry = 100
bantime = 600
findtime = 60
```

### Custom Filters
- **nginx-http-auth**: Authentication failure detection
- **nginx-limit-req**: Rate limiting violation detection
- **nginx-noscript**: Script kiddie attempt blocking
- **nginx-badbots**: Malicious bot identification
- **nginx-botsearch**: Exploit search detection
- **nginx-4xx**: Excessive 4xx error detection

## Monitoring and Alerting

### Key Metrics
- **Request Rate**: `rate(nginx_http_requests_total[5m])`
- **Rate Limited Requests**: `nginx_http_requests_total{status="429"}`
- **Blocked Requests**: `nginx_http_requests_total{status="403"}`
- **Active Connections**: `nginx_connections_active`
- **Security Events**: Custom metrics from security logs

### Alerting Rules
```yaml
- alert: HighRateLimitingActivity
  expr: rate(nginx_http_requests_total{status="429"}[5m]) > 10
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High rate limiting activity detected"

- alert: DDoSAttackDetected
  expr: rate(nginx_http_requests_total[1m]) > 1000
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Potential DDoS attack detected"
```

## Deployment Instructions

### Prerequisites
```bash
# Ensure Kubernetes cluster is running
kubectl cluster-info

# Create namespace
kubectl create namespace neuronews

# Optional: Set up GeoIP credentials
export GEOIP_ACCOUNT_ID="your-account-id"
export GEOIP_LICENSE_KEY="your-license-key"
```

### 1. Deploy Configuration
```bash
# Apply NGINX rate limiting configuration
kubectl apply -f k8s/nginx/rate-limiting-configmap.yaml

# Apply Fail2ban configuration
kubectl apply -f k8s/security/fail2ban-configmap.yaml

# Apply Fluentd security logging configuration
kubectl apply -f k8s/security/fluentd-security-configmap.yaml
```

### 2. Deploy DDoS Protection Stack
```bash
# Create GeoIP credentials secret (optional)
kubectl create secret generic geoip-credentials \
    --from-literal=account-id="${GEOIP_ACCOUNT_ID}" \
    --from-literal=license-key="${GEOIP_LICENSE_KEY}" \
    -n neuronews

# Deploy NGINX with DDoS protection
kubectl apply -f k8s/nginx/ddos-protection-deployment.yaml

# Deploy services and network policies
kubectl apply -f k8s/nginx/ddos-protection-service.yaml
```

### 3. Verify Deployment
```bash
# Check all pods are running
kubectl get pods -n neuronews

# Check services
kubectl get svc -n neuronews

# Check logs
kubectl logs -n neuronews deployment/nginx-ddos-protection -c nginx
kubectl logs -n neuronews deployment/nginx-ddos-protection -c fail2ban
```

## Testing the DDoS Protection

### 1. Run Comprehensive Tests
```bash
# Run the complete test suite
./test_ddos_protection.sh

# Run with custom parameters
./test_ddos_protection.sh --duration 600 --connections 500 --rps 1000
```

### 2. Manual Testing
```bash
# Get service URL
NGINX_URL=$(kubectl get svc nginx-ddos-protection-loadbalancer -n neuronews -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test rate limiting
for i in {1..150}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://$NGINX_URL/api/v1/news
done

# Test bot detection
curl -A "curl/7.68.0" http://$NGINX_URL/api/v1/news
curl -A "python-requests/2.25.1" http://$NGINX_URL/api/v1/news

# Test suspicious paths
curl http://$NGINX_URL/admin
curl http://$NGINX_URL/wp-admin
curl http://$NGINX_URL/.env
```

### 3. Load Testing
```bash
# Use Apache Bench for load testing
ab -n 10000 -c 100 -t 60 http://$NGINX_URL/api/v1/health

# Use siege for complex scenarios
siege -c 50 -t 5m http://$NGINX_URL/api/v1/news
```

## Security Event Analysis

### Log Analysis
```bash
# View rate limiting events
kubectl logs -n neuronews deployment/nginx-ddos-protection -c nginx | grep "limiting requests"

# View blocked requests
kubectl logs -n neuronews deployment/nginx-ddos-protection -c nginx | grep " 403 \| 429 "

# View fail2ban actions
kubectl logs -n neuronews deployment/nginx-ddos-protection -c fail2ban | grep "Ban\|Unban"
```

### Metrics Analysis
```bash
# Port forward to metrics endpoint
kubectl port-forward -n neuronews svc/nginx-ddos-protection-service 9113:9113

# Query security metrics
curl -s http://localhost:9113/metrics | grep "nginx_http_requests_total.*429"
curl -s http://localhost:9113/metrics | grep "nginx_connections_active"
```

## Performance Optimization

### High Traffic Scenarios
- Increase NGINX worker processes based on CPU cores
- Adjust rate limiting thresholds based on legitimate traffic patterns
- Implement connection pooling and keep-alive optimization
- Use efficient log rotation and compression

### Resource Optimization
```yaml
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 512Mi
```

### Scaling Configuration
```yaml
replicas: 3  # High availability setup
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 1
    maxSurge: 1
```

## Security Best Practices

### Configuration Security
- Use minimal required permissions for service accounts
- Implement network policies for pod-to-pod communication
- Regular security updates for base images
- Secure storage of sensitive configuration data

### Monitoring and Alerting
- Set up real-time alerting for security events
- Implement automated response procedures
- Regular security audit and penetration testing
- Maintain incident response documentation

### Maintenance Procedures
- Regular review and tuning of rate limiting thresholds
- Update IP blacklists and threat intelligence feeds
- Monitor false positive rates and adjust filters
- Backup and version control for security configurations

## Troubleshooting

### Common Issues

1. **Rate Limiting Too Aggressive**
   ```bash
   # Check current limits
   kubectl get configmap nginx-rate-limiting-config -n neuronews -o yaml
   
   # Adjust limits in configmap and restart pods
   kubectl rollout restart deployment/nginx-ddos-protection -n neuronews
   ```

2. **Fail2ban Not Working**
   ```bash
   # Check fail2ban status
   kubectl logs -n neuronews deployment/nginx-ddos-protection -c fail2ban
   
   # Verify iptables rules
   kubectl exec -it deployment/nginx-ddos-protection -c fail2ban -- iptables -L
   ```

3. **High Memory Usage**
   ```bash
   # Monitor resource usage
   kubectl top pods -n neuronews
   
   # Adjust resource limits if needed
   kubectl patch deployment nginx-ddos-protection -n neuronews -p '{"spec":{"template":{"spec":{"containers":[{"name":"nginx","resources":{"limits":{"memory":"1Gi"}}}]}}}}'
   ```

### Debug Commands
```bash
# Test NGINX configuration
kubectl exec -n neuronews deployment/nginx-ddos-protection -c nginx -- nginx -t

# Check rate limiting zones
kubectl exec -n neuronews deployment/nginx-ddos-protection -c nginx -- nginx -T | grep limit_req_zone

# View active connections
kubectl exec -n neuronews deployment/nginx-ddos-protection -c nginx -- curl localhost/nginx_status
```

## Security Compliance

### Industry Standards
- **OWASP Top 10**: Protection against common web vulnerabilities
- **DDoS Mitigation**: Industry-standard rate limiting and traffic shaping
- **PCI DSS**: Compliance for payment processing environments
- **GDPR**: Privacy protection and data handling compliance

### Audit and Reporting
- Automated security scanning and vulnerability assessment
- Regular penetration testing and security audits
- Compliance reporting and documentation
- Incident response and forensic capabilities

## Integration with Existing Security Stack

### SIEM Integration
```yaml
# Fluentd output to SIEM
<match security.**>
  @type syslog
  host siem.company.com
  port 514
  facility local0
  severity info
</match>
```

### Threat Intelligence
- Integration with threat intelligence feeds
- Automated IP reputation checking
- Real-time threat indicator updates
- Collaborative defense mechanisms

This comprehensive DDoS protection implementation provides enterprise-grade security for the NeuroNews API while maintaining optimal performance for legitimate users.
