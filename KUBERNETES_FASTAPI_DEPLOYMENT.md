# NeuroNews FastAPI Kubernetes Deployment - Issue #72

## 🎯 Overview

Complete Kubernetes deployment of the NeuroNews FastAPI server with enterprise-grade features including auto-scaling, health checks, load balancing, and comprehensive monitoring.

## 📋 Issue #72 Requirements ✅

### ✅ 1. Create Kubernetes Deployment & Service for FastAPI
- **Kubernetes Deployment**: Production-ready deployment with 3 replicas
- **Kubernetes Service**: LoadBalancer and ClusterIP services for internal/external access
- **Security**: Non-root containers, RBAC, Network Policies, Pod Security Standards

### ✅ 2. Expose API via LoadBalancer or Ingress Controller
- **LoadBalancer Service**: AWS NLB integration with SSL termination
- **Ingress Controller**: NGINX Ingress with SSL, rate limiting, and CORS
- **DNS**: Support for custom domains with TLS certificates
- **Load Balancing**: Round-robin with session affinity options

### ✅ 3. Implement Horizontal Pod Autoscaler (HPA)
- **CPU-based scaling**: 70% CPU utilization threshold
- **Memory-based scaling**: 80% memory utilization threshold
- **Custom metrics**: HTTP requests per second scaling
- **Vertical Pod Autoscaler**: Automatic resource optimization

### ✅ 4. Configure readiness & liveness probes for self-healing
- **Liveness Probe**: Health check every 30s with failure tolerance
- **Readiness Probe**: Ready check every 10s for traffic routing
- **Startup Probe**: Slow startup protection with 30 retries
- **Health Endpoints**: Comprehensive `/health` endpoint monitoring

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet / External Users                │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 Load Balancer (AWS NLB)                     │
│  • SSL Termination     • Health Checks     • Multi-AZ      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                 Ingress Controller (NGINX)                  │
│  • Rate Limiting       • CORS           • Compression       │
│  • SSL/TLS             • Path Routing   • WebSocket        │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Pod Cluster (3-20 replicas)           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  FastAPI    │  │  FastAPI    │  │  FastAPI    │         │
│  │  Pod 1      │  │  Pod 2      │  │  Pod 3      │         │
│  │             │  │             │  │             │         │
│  │ CPU: 200m   │  │ CPU: 200m   │  │ CPU: 200m   │         │
│  │ Mem: 512Mi  │  │ Mem: 512Mi  │  │ Mem: 512Mi  │         │
│  │ Port: 8000  │  │ Port: 8000  │  │ Port: 8000  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                   Data Layer                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ PostgreSQL  │  │    Redis    │  │   Gremlin   │         │
│  │  Database   │  │    Cache    │  │ Graph DB    │         │
│  │             │  │             │  │             │         │
│  │ Port: 5432  │  │ Port: 6379  │  │ Port: 8182  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘

            ┌─────────────────────────────────────────┐
            │         Monitoring & Observability      │
            │  ┌─────────────┐  ┌─────────────┐       │
            │  │ Prometheus  │  │   Grafana   │       │
            │  │  Metrics    │  │ Dashboards  │       │
            │  │             │  │             │       │
            │  │ Port: 9090  │  │ Port: 3000  │       │
            │  └─────────────┘  └─────────────┘       │
            └─────────────────────────────────────────┘
```

## 📁 Kubernetes Resources

### Core Deployment
- **`k8s/fastapi/namespace.yaml`** - Namespace, RBAC, Network Policies
- **`k8s/fastapi/deployment.yaml`** - FastAPI Deployment with ServiceAccount
- **`k8s/fastapi/service.yaml`** - LoadBalancer and ClusterIP services
- **`k8s/fastapi/configmap.yaml`** - Configuration and Secrets

### Auto-scaling & Policies
- **`k8s/fastapi/hpa.yaml`** - Horizontal & Vertical Pod Autoscalers
- **`k8s/fastapi/policies.yaml`** - Pod Disruption Budget, Limits, Quotas

### Traffic Management
- **`k8s/fastapi/ingress.yaml`** - NGINX Ingress with SSL and rate limiting

### Monitoring & Observability
- **`k8s/fastapi/monitoring.yaml`** - ServiceMonitor, Grafana Dashboard, Alerts

### Automation
- **`scripts/deploy-k8s-fastapi.sh`** - Comprehensive deployment script
- **`k8s/kustomization.yaml`** - Kustomize configuration for environments

## 🚀 Quick Start

### Prerequisites
```bash
# Required tools
kubectl version --client
helm version
docker version

# Kubernetes cluster access
kubectl cluster-info
kubectl get nodes
```

### 1. Deploy with Script (Recommended)
```bash
# Deploy everything
./scripts/deploy-k8s-fastapi.sh deploy

# Check status
./scripts/deploy-k8s-fastapi.sh status

# View logs
./scripts/deploy-k8s-fastapi.sh logs

# Scale deployment
./scripts/deploy-k8s-fastapi.sh scale 5
```

### 2. Manual Deployment
```bash
# Create namespace and RBAC
kubectl apply -f k8s/fastapi/namespace.yaml

# Deploy configurations
kubectl apply -f k8s/fastapi/configmap.yaml

# Deploy application
kubectl apply -f k8s/fastapi/deployment.yaml
kubectl apply -f k8s/fastapi/service.yaml

# Setup auto-scaling
kubectl apply -f k8s/fastapi/hpa.yaml
kubectl apply -f k8s/fastapi/policies.yaml

# Configure ingress
kubectl apply -f k8s/fastapi/ingress.yaml

# Setup monitoring
kubectl apply -f k8s/fastapi/monitoring.yaml
```

### 3. Using Kustomize
```bash
# Deploy with kustomize
kubectl apply -k k8s/

# Deploy to specific environment
kubectl apply -k k8s/ --namespace=neuronews-staging
```

## 🔧 Configuration

### Environment Variables
```bash
# Required Configuration
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Database Configuration
DB_HOST=postgres-service
DB_PORT=5432
DB_NAME=neuronews
DB_USER=neuronews
DB_PASSWORD=secure_password

# Cache Configuration
REDIS_HOST=redis-service
REDIS_PORT=6379

# Security
JWT_SECRET_KEY=your_jwt_secret

# AWS Integration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
```

### Resource Configuration
```yaml
# Pod Resources
requests:
  cpu: 200m      # 0.2 CPU cores
  memory: 512Mi  # 512 MB RAM
limits:
  cpu: 1000m     # 1 CPU core
  memory: 2Gi    # 2 GB RAM

# Scaling Limits
minReplicas: 3   # Minimum pods
maxReplicas: 20  # Maximum pods
```

### Health Check Configuration
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 30
  
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
```

## 📊 Monitoring & Observability

### Prometheus Metrics
- **HTTP Requests**: Total requests, rate, duration
- **System Metrics**: CPU, memory, disk usage
- **Application Metrics**: Database connections, cache hits
- **Custom Metrics**: Business logic metrics

### Grafana Dashboards
- **API Performance**: Request rate, response time, error rate
- **System Health**: CPU, memory, network usage
- **Auto-scaling**: Pod count, scaling events
- **Alerts**: Real-time alerting for critical issues

### Health Endpoints
```bash
# Health check
curl http://api.neuronews.io/health

# Metrics endpoint
curl http://api.neuronews.io/metrics

# API documentation
curl http://api.neuronews.io/docs
```

### Alerts Configuration
- **High Error Rate**: >5% errors for 2 minutes
- **High Latency**: >2s 95th percentile for 5 minutes
- **Pod Down**: <2 pods running for 1 minute
- **Resource Usage**: >80% CPU/memory for 5 minutes

## 🔄 Auto-scaling

### Horizontal Pod Autoscaler (HPA)
```yaml
# CPU-based scaling
- CPU utilization > 70% → Scale up
- CPU utilization < 50% → Scale down

# Memory-based scaling
- Memory utilization > 80% → Scale up
- Memory utilization < 60% → Scale down

# Custom metrics scaling
- HTTP requests/sec > 100 → Scale up
- HTTP requests/sec < 50 → Scale down
```

### Vertical Pod Autoscaler (VPA)
```yaml
# Automatic resource optimization
- Monitors actual CPU/memory usage
- Adjusts requests/limits automatically
- Prevents over/under-provisioning
```

### Scaling Behavior
```yaml
scaleUp:
  stabilizationWindowSeconds: 60
  policies:
    - type: Percent
      value: 50%    # Max 50% increase
    - type: Pods
      value: 4      # Max 4 pods at once

scaleDown:
  stabilizationWindowSeconds: 300
  policies:
    - type: Percent
      value: 10%    # Max 10% decrease
    - type: Pods
      value: 2      # Max 2 pods at once
```

## 🔒 Security Features

### Pod Security
- **Non-root user**: Runs as UID 1000, GID 1000
- **Read-only filesystem**: Where applicable
- **Security context**: Restricted capabilities
- **Resource limits**: CPU and memory constraints

### Network Security
- **Network Policies**: Ingress/egress traffic control
- **Service Mesh**: Optional Istio integration
- **TLS encryption**: End-to-end encryption
- **RBAC**: Role-based access control

### Secrets Management
- **Kubernetes Secrets**: Encrypted at rest
- **External Secrets**: Integration with AWS Secrets Manager
- **Service Account**: IAM role binding for AWS
- **Secret rotation**: Automatic secret updates

## 🌐 Load Balancing & Traffic Management

### LoadBalancer Service
```yaml
# AWS Network Load Balancer
annotations:
  service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
  service.beta.kubernetes.io/aws-load-balancer-ssl-cert: "cert-arn"
  service.beta.kubernetes.io/aws-load-balancer-cross-zone-load-balancing-enabled: "true"
```

### Ingress Controller
```yaml
# NGINX Ingress with advanced features
annotations:
  nginx.ingress.kubernetes.io/rate-limit: "100"
  nginx.ingress.kubernetes.io/ssl-redirect: "true"
  nginx.ingress.kubernetes.io/cors-allow-origin: "*"
  nginx.ingress.kubernetes.io/load-balance: "round_robin"
```

### Session Affinity
```yaml
# Sticky sessions (optional)
sessionAffinity: ClientIP
sessionAffinityConfig:
  clientIP:
    timeoutSeconds: 10800  # 3 hours
```

## 🧪 Testing & Validation

### Deployment Testing
```bash
# Check all resources
kubectl get all -n neuronews

# Validate deployment
kubectl rollout status deployment/neuronews-fastapi -n neuronews

# Test connectivity
kubectl run test-curl --image=curlimages/curl --rm -it --restart=Never -- \
  curl -f http://neuronews-fastapi-service.neuronews.svc.cluster.local:8000/health
```

### Load Testing
```bash
# Using kubectl run with curl
kubectl run load-test --image=curlimages/curl --rm -it --restart=Never -- \
  sh -c 'for i in $(seq 1 100); do curl -f http://neuronews-fastapi-service.neuronews.svc.cluster.local:8000/health; done'

# Using external load testing tools
hey -n 1000 -c 10 http://api.neuronews.io/health
```

### Health Validation
```bash
# Check pod health
kubectl get pods -n neuronews -l app=neuronews-fastapi

# Check HPA status
kubectl get hpa -n neuronews

# Check events
kubectl get events -n neuronews --sort-by='.lastTimestamp'
```

## 🚨 Troubleshooting

### Common Issues

#### Pods not starting
```bash
# Check pod status
kubectl describe pod <pod-name> -n neuronews

# Check logs
kubectl logs <pod-name> -n neuronews

# Check events
kubectl get events -n neuronews
```

#### HPA not scaling
```bash
# Check metrics server
kubectl get apiservice v1beta1.metrics.k8s.io

# Check HPA status
kubectl describe hpa neuronews-fastapi-hpa -n neuronews

# Install metrics server if missing
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

#### Ingress not working
```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Check ingress status
kubectl describe ingress neuronews-fastapi-ingress -n neuronews

# Check DNS resolution
nslookup api.neuronews.io
```

#### Database connectivity
```bash
# Test database connection
kubectl run db-test --image=postgres:13 --rm -it --restart=Never -- \
  psql -h postgres-service.neuronews.svc.cluster.local -U neuronews -d neuronews
```

### Debug Commands
```bash
# Get detailed status
./scripts/deploy-k8s-fastapi.sh status

# Check recent logs
./scripts/deploy-k8s-fastapi.sh logs 500

# Scale for debugging
./scripts/deploy-k8s-fastapi.sh scale 1

# Port forward for local access
kubectl port-forward service/neuronews-fastapi-service -n neuronews 8000:80
```

## 🔄 Updates & Maintenance

### Rolling Updates
```bash
# Update image
kubectl set image deployment/neuronews-fastapi fastapi=neuronews/fastapi:v1.1.0 -n neuronews

# Monitor rollout
kubectl rollout status deployment/neuronews-fastapi -n neuronews

# Rollback if needed
kubectl rollout undo deployment/neuronews-fastapi -n neuronews
```

### Configuration Updates
```bash
# Update ConfigMap
kubectl apply -f k8s/fastapi/configmap.yaml

# Restart deployment to pick up changes
kubectl rollout restart deployment/neuronews-fastapi -n neuronews
```

### Scaling Operations
```bash
# Manual scaling
kubectl scale deployment neuronews-fastapi --replicas=5 -n neuronews

# Update HPA limits
kubectl patch hpa neuronews-fastapi-hpa -n neuronews -p '{"spec":{"maxReplicas":25}}'
```

## 🎯 Issue #72 Completion Summary

### ✅ **All Requirements Successfully Implemented**

#### 1. ✅ **Kubernetes Deployment & Service for FastAPI** 
- **Production Deployment**: 3-replica deployment with advanced configuration
- **Service Types**: LoadBalancer for external access, ClusterIP for internal
- **Security**: RBAC, Network Policies, Pod Security Standards
- **Resource Management**: Requests, limits, and quotas

#### 2. ✅ **LoadBalancer & Ingress Controller** 
- **AWS NLB Integration**: SSL termination, cross-zone load balancing
- **NGINX Ingress**: Advanced features with rate limiting, CORS, compression
- **TLS/SSL**: Automatic certificate management with cert-manager
- **Multiple Domains**: Support for api.neuronews.io and custom domains

#### 3. ✅ **Horizontal Pod Autoscaler (HPA)** 
- **Multi-metric Scaling**: CPU (70%), Memory (80%), Custom metrics
- **Intelligent Policies**: Scale-up/down behaviors with stabilization
- **VPA Integration**: Vertical scaling for resource optimization
- **Production Tuning**: 3-20 replica range with performance policies

#### 4. ✅ **Readiness & Liveness Probes** 
- **Comprehensive Health Checks**: Startup, readiness, and liveness probes
- **Self-healing**: Automatic pod restart on failure
- **Traffic Management**: Ready pods receive traffic automatically
- **Graceful Degradation**: Smooth handling of unhealthy instances

### 🏆 **Enterprise-Grade Features**
- ✅ **High Availability**: Multi-replica deployment with anti-affinity
- ✅ **Auto-scaling**: Horizontal and vertical scaling automation
- ✅ **Monitoring**: Prometheus metrics, Grafana dashboards, alerting
- ✅ **Security**: RBAC, Network Policies, encrypted secrets
- ✅ **Load Balancing**: Advanced traffic management and distribution
- ✅ **Self-healing**: Automatic recovery from failures
- ✅ **CI/CD Ready**: Integration with GitOps and automated deployments

**Issue #72 is COMPLETE with production-ready Kubernetes deployment! 🚀**

The FastAPI server is now running in Kubernetes with enterprise-grade auto-scaling, health checks, and comprehensive monitoring - ready for production workloads!

## 📖 Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [NGINX Ingress Controller](https://kubernetes.github.io/ingress-nginx/)
- [Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Prometheus Monitoring](https://prometheus.io/docs/)
- [AWS Load Balancer Controller](https://kubernetes-sigs.github.io/aws-load-balancer-controller/)

**The NeuroNews FastAPI Kubernetes deployment provides a robust, scalable, and secure foundation for cloud-native operations! 🎉**
