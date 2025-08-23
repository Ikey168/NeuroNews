# Kubernetes Scrapers Deployment Guide

## Overview

This guide covers the deployment and management of NeuroNews scrapers as Kubernetes CronJobs, implementing Issue #73 requirements:

- ✅ Convert scrapers to Kubernetes CronJobs

- ✅ Schedule scrapers (hourly/daily patterns)

- ✅ Implement logging and retry mechanisms

- ✅ Optimize resource allocation and monitoring

## Architecture

### CronJob Design

```text

├── News Scraper CronJob (Every 4 hours)
├── Tech Scraper CronJob (Every 6 hours)
├── AI Scraper CronJob (Every 8 hours)
├── Metrics Collector CronJob (Every 5 minutes)
└── RBAC & Resource Management

```text

### Resource Strategy

- **Memory**: 512Mi requests, 1Gi limits

- **CPU**: 200m requests, 500m limits

- **Concurrency**: Prohibit concurrent jobs

- **Retention**: 3 successful, 1 failed job history

## Quick Start

### Prerequisites

- Kubernetes cluster (v1.19+)

- kubectl configured

- Docker images available

- Monitoring stack (Prometheus/Grafana)

### 1. Deploy Scrapers

```bash

# Deploy all scraper components

./scripts/deploy-k8s-scrapers.sh deploy

# Check deployment status

./scripts/deploy-k8s-scrapers.sh status

```text

### 2. Verify Deployment

```bash

# Validate all components

./scripts/deploy-k8s-scrapers.sh validate

# Monitor job execution

./scripts/deploy-k8s-scrapers.sh monitor

```text

### 3. Manual Job Execution

```bash

# Trigger news scraper manually

./scripts/deploy-k8s-scrapers.sh trigger news

# Trigger tech scraper manually

./scripts/deploy-k8s-scrapers.sh trigger tech

# Trigger AI scraper manually

./scripts/deploy-k8s-scrapers.sh trigger ai

```text

## Deployment Components

### 1. CronJobs (`k8s/scrapers/cronjobs.yaml`)

#### News Scraper

- **Schedule**: `0 */4 * * *` (Every 4 hours)

- **Image**: `neuronews/news-scraper:latest`

- **Resources**: 512Mi memory, 200m CPU

- **Retry**: 3 attempts with exponential backoff

#### Tech Scraper

- **Schedule**: `0 */6 * * *` (Every 6 hours)

- **Image**: `neuronews/tech-scraper:latest`

- **Resources**: 512Mi memory, 200m CPU

- **Retry**: 3 attempts with exponential backoff

#### AI Scraper

- **Schedule**: `0 */8 * * *` (Every 8 hours)

- **Image**: `neuronews/ai-scraper:latest`

- **Resources**: 512Mi memory, 200m CPU

- **Retry**: 3 attempts with exponential backoff

### 2. RBAC (`k8s/scrapers/rbac.yaml`)

- ServiceAccount: `neuronews-scrapers`

- Role: Job management, secret access, metric collection

- RoleBinding: Secure service account binding

### 3. Configuration (`k8s/scrapers/configmap.yaml`)

- Environment variables

- Scraping parameters

- Rate limiting configuration

- Output settings

### 4. Security Policies (`k8s/scrapers/policies.yaml`)

- Network policies for controlled egress

- Pod security standards enforcement

- Resource quotas and limits

### 5. Monitoring (`k8s/scrapers/monitoring.yaml`)

- Prometheus ServiceMonitor

- Grafana dashboard configuration

- Alert rules and notifications

- Metrics collection CronJob

## Configuration

### Environment Variables

```yaml

# Core Configuration

NEWS_SOURCES: "reuters,bbc,cnn,ap"
TECH_SOURCES: "techcrunch,arstechnica,wired"
AI_SOURCES: "openai,anthropic,google-ai"

# Rate Limiting

RATE_LIMIT_REQUESTS: "100"
RATE_LIMIT_WINDOW: "3600"
CONCURRENT_SCRAPERS: "5"

# Storage

OUTPUT_FORMAT: "json"
S3_BUCKET: "neuronews-data"
COMPRESSION_ENABLED: "true"

# Monitoring

METRICS_ENABLED: "true"
LOG_LEVEL: "INFO"
HEALTH_CHECK_INTERVAL: "30"

```text

### Schedule Patterns

```yaml

# Optimal distribution to avoid resource conflicts

News Scraper:    "0 */4 * * *"   # 00:00, 04:00, 08:00, 12:00, 16:00, 20:00

Tech Scraper:    "0 */6 * * *"   # 00:00, 06:00, 12:00, 18:00

AI Scraper:      "0 */8 * * *"   # 00:00, 08:00, 16:00

Metrics:         "*/5 * * * *"   # Every 5 minutes

# Peak hours consideration (EST)

# Morning: 06:00-09:00 (News + Metrics)

# Midday: 12:00-15:00 (News + Tech + Metrics)

# Evening: 18:00-21:00 (Tech + Metrics)

```text

## Management Commands

### Deployment Operations

```bash

# Full deployment

./scripts/deploy-k8s-scrapers.sh deploy

# Check status and schedules

./scripts/deploy-k8s-scrapers.sh status

# Validate configuration

./scripts/deploy-k8s-scrapers.sh validate

```text

### Job Control

```bash

# Suspend all CronJobs

./scripts/deploy-k8s-scrapers.sh suspend

# Resume all CronJobs

./scripts/deploy-k8s-scrapers.sh resume

# Trigger manual execution

./scripts/deploy-k8s-scrapers.sh trigger news
./scripts/deploy-k8s-scrapers.sh trigger tech
./scripts/deploy-k8s-scrapers.sh trigger ai

```text

### Monitoring & Logs

```bash

# Real-time monitoring

./scripts/deploy-k8s-scrapers.sh monitor

# View logs (all scrapers)

./scripts/deploy-k8s-scrapers.sh logs

# View specific scraper logs

./scripts/deploy-k8s-scrapers.sh logs news 500
./scripts/deploy-k8s-scrapers.sh logs tech 200

```text

### Maintenance

```bash

# Clean up failed jobs

./scripts/deploy-k8s-scrapers.sh cleanup-failed

# Complete cleanup (removes all resources)

./scripts/deploy-k8s-scrapers.sh cleanup

```text

## Monitoring & Observability

### Grafana Dashboard Panels

1. **Active Jobs**: Currently running scraper jobs

2. **Success Rate**: Job completion success percentage

3. **Resource Usage**: CPU and memory consumption

4. **Articles Scraped**: Total articles collected per period

5. **Execution Duration**: Job runtime metrics

6. **Failed Jobs**: Error tracking and analysis

7. **CronJob Status**: Schedule adherence monitoring

8. **Network Traffic**: Data transfer metrics

### Prometheus Metrics

```promql

# Job success rate

rate(cronjob_job_successful_total[5m])

# Job duration

histogram_quantile(0.95, rate(cronjob_job_duration_seconds_bucket[5m]))

# Resource usage

container_memory_usage_bytes{container="scraper"}
rate(container_cpu_usage_seconds_total{container="scraper"}[5m])

# Articles scraped

increase(scraper_articles_total[1h])

```text

### Alert Rules

- **Job Failure**: >50% failure rate in 1 hour

- **High Error Rate**: >10% errors in 30 minutes

- **Low Productivity**: <50 articles in 4 hours

- **Stuck Jobs**: Job running >2 hours

- **Memory Usage**: >90% memory utilization

- **CronJob Not Running**: No execution in expected window

## Troubleshooting

### Common Issues

#### CronJob Not Starting

```bash

# Check CronJob status

kubectl get cronjobs -n neuronews -l app=neuronews-scrapers

# Check events

kubectl describe cronjob neuronews-news-scraper -n neuronews

# Verify RBAC

kubectl auth can-i create jobs --as=system:serviceaccount:neuronews:neuronews-scrapers -n neuronews

```text

#### Pod Failures

```bash

# Check pod logs

kubectl logs -n neuronews -l component=news-scraper --tail=100

# Check resource constraints

kubectl describe pod -n neuronews -l component=news-scraper

# Check node resources

kubectl top nodes

```text

#### Network Issues

```bash

# Test external connectivity

kubectl run test-pod --image=alpine --rm -it -- wget -O- https://www.reuters.com

# Check network policies

kubectl get networkpolicies -n neuronews

# Verify DNS resolution

kubectl run test-dns --image=alpine --rm -it -- nslookup google.com

```text

#### Resource Constraints

```bash

# Check resource quotas

kubectl get resourcequota -n neuronews

# Monitor resource usage

kubectl top pods -n neuronews -l app=neuronews-scrapers

# Check limit ranges

kubectl get limitrange -n neuronews

```text

### Performance Optimization

#### Memory Optimization

```yaml

# Adjust resource requests/limits

resources:
  requests:
    memory: "256Mi"  # Reduce for lighter workloads

    cpu: "100m"
  limits:
    memory: "1Gi"    # Increase for heavy processing

    cpu: "500m"

```text

#### Schedule Optimization

```yaml

# Spread jobs to avoid resource conflicts

spec:
  schedule: "{{ randInt 0 59 }} */4 * * *"  # Random minute offset

  concurrencyPolicy: Forbid                  # Prevent overlaps

  startingDeadlineSeconds: 3600             # Allow 1 hour delay

```text

#### Retry Strategy

```yaml

# Configure job retry behavior

spec:
  backoffLimit: 3                    # Max 3 retries

  activeDeadlineSeconds: 7200        # 2 hour timeout

  ttlSecondsAfterFinished: 86400     # Clean up after 24 hours

```text

## Security Considerations

### Network Security

- Egress-only network policies

- Restricted external access

- DNS-based service discovery

### Pod Security

- Non-root user execution

- Read-only root filesystem

- Security context constraints

### RBAC Configuration

- Minimal required permissions

- Service account isolation

- Namespace boundary enforcement

### Secret Management

- Kubernetes secrets for credentials

- Automatic secret rotation

- Encryption at rest

## Migration from Direct Execution

### From Cron Jobs

```bash

# Disable existing cron jobs

sudo crontab -l | grep -v neuronews | crontab -

# Migrate schedules to Kubernetes

# Existing: 0 */4 * * * /path/to/scraper.py news

# New: CronJob with same schedule in Kubernetes

```text

### From Docker Compose

```bash

# Stop existing containers

docker-compose down

# Deploy to Kubernetes

./scripts/deploy-k8s-scrapers.sh deploy

```text

### Data Migration

```bash

# Backup existing data

kubectl create job data-backup --from=cronjob/neuronews-news-scraper

# Verify data consistency

kubectl logs job/data-backup

```text

## Best Practices

### Resource Management

- Set appropriate resource requests and limits

- Use horizontal pod autoscaling for variable loads

- Monitor resource utilization trends

### Scheduling Strategy

- Distribute job execution times

- Consider business hours and peak usage

- Use timezone-aware scheduling

### Error Handling

- Implement exponential backoff

- Log errors for debugging

- Set up proper alerting

### Monitoring

- Track key performance indicators

- Set up proactive alerts

- Regular performance reviews

### Security

- Follow principle of least privilege

- Regular security assessments

- Keep images updated

## Support

### Logs Location

- **Kubernetes Logs**: `kubectl logs -n neuronews -l app=neuronews-scrapers`

- **Job History**: Available through Kubernetes events

- **Metrics**: Prometheus/Grafana dashboards

### Key Files

- **CronJobs**: `k8s/scrapers/cronjobs.yaml`

- **Configuration**: `k8s/scrapers/configmap.yaml`

- **RBAC**: `k8s/scrapers/rbac.yaml`

- **Monitoring**: `k8s/scrapers/monitoring.yaml`

- **Deployment Script**: `scripts/deploy-k8s-scrapers.sh`

### Useful Commands

```bash

# Get help

./scripts/deploy-k8s-scrapers.sh help

# Quick status check

kubectl get cronjobs,jobs,pods -n neuronews -l app=neuronews-scrapers

# Real-time job monitoring

watch "kubectl get jobs -n neuronews -l app=neuronews-scrapers"

```text

---

**Issue #73 Implementation Complete**: All requirements fulfilled with enterprise-grade Kubernetes CronJob deployment, comprehensive monitoring, and operational tooling.
