# NeuroNews Deployment Scripts

This directory contains comprehensive deployment automation scripts for the NeuroNews Kubernetes CI/CD pipeline.

## Scripts Overview

### 1. deploy-canary.sh

**Purpose**: Automated canary deployment with progressive traffic management

**Features**:

- Progressive traffic shifting (10% → 25% → 50% → 75% → 100%)

- Automated health monitoring and validation

- Auto-promotion and rollback capabilities

- Support for all services (api, dashboard, scraper, nlp-processor)

- Dry-run mode for testing

- Comprehensive logging and reporting

**Usage Examples**:

```bash

# Deploy API service with canary strategy

./deploy-canary.sh --service api --image-tag v1.2.3 --traffic-percentage 25

# Deploy all services with auto-promotion

./deploy-canary.sh --service all --image-tag main-abc123 --auto-promote

# Dry run for dashboard deployment

./deploy-canary.sh --service dashboard --image-tag v2.0.0 --dry-run

```text

### 2. deploy-production.sh

**Purpose**: Zero-downtime rolling deployments for production environment

**Features**:

- Rolling update strategy with configurable parameters

- Pre and post-deployment health checks

- Automatic rollback on failure (optional)

- Resource validation and safety checks

- Deployment reporting and metrics

- Support for recreate strategy when needed

**Usage Examples**:

```bash

# Deploy API with rolling updates

./deploy-production.sh --service api --image-tag v1.2.3

# Deploy all services with rollback protection

./deploy-production.sh --service all --image-tag stable-release --rollback-on-failure

# Emergency deployment with recreate strategy

./deploy-production.sh --service nlp-processor --image-tag hotfix-123 --strategy recreate

```text

### 3. health-check.sh

**Purpose**: Comprehensive health monitoring for all deployed services

**Features**:

- HTTP endpoint health checks

- Kubernetes deployment and pod status monitoring

- Continuous monitoring mode

- JSON output for integration with monitoring systems

- Metrics export and alerting

- Service-specific and multi-service checks

**Usage Examples**:

```bash

# Check health of all services

./health-check.sh --service all

# Continuous monitoring with 30s intervals

./health-check.sh --continuous --interval 30

# JSON output for monitoring integration

./health-check.sh --json --export-metrics

# Detailed health information

./health-check.sh --service api --detailed

```text

### 4. rollback.sh

**Purpose**: Automated rollback functionality with safety checks

**Features**:

- Rollback to previous or specific revision

- Pre-rollback safety validation

- Emergency rollback mode (skip safety checks)

- Revision history listing and management

- Post-rollback health verification

- Comprehensive rollback reporting

**Usage Examples**:

```bash

# Rollback API to previous version

./rollback.sh --service api

# Rollback to specific revision

./rollback.sh --service dashboard --revision 5

# Emergency rollback with auto-confirmation

./rollback.sh --service all --emergency

# List available revisions

./rollback.sh --list-revisions --service api

```text

## Common Parameters

All scripts support these common parameters:

- `--namespace, -n`: Kubernetes namespace (default: neuronews)

- `--help, -h`: Show help information

- `--dry-run`: Preview actions without execution

- `--wait-timeout`: Timeout for waiting operations

## Environment Configuration

### Environment Variables

- `NAMESPACE`: Default Kubernetes namespace

- `REGISTRY`: Container registry URL

- `HEALTH_CHECK_URL`: Base URL for health checks

- `ROLLBACK_REASON`: Reason for rollback operations

### Prerequisites

1. **kubectl**: Kubernetes CLI tool

2. **argo-rollouts CLI**: For canary deployments

3. **curl**: For HTTP health checks

4. **bc**: For mathematical calculations

### Installation

```bash

# Make all scripts executable

chmod +x scripts/deployment/*.sh

# Add to PATH (optional)

export PATH=$PATH:$(pwd)/scripts/deployment

```text

## Integration with CI/CD

These scripts are designed to integrate with the GitHub Actions workflows:

### PR Validation Workflow

- Uses `health-check.sh` for validation

- Integrates with staging environment testing

### Canary Deployment Workflow

- Uses `deploy-canary.sh` for progressive deployments

- Automated promotion/rollback based on health checks

- Monitoring integration for decision making

### Production Deployment

- Uses `deploy-production.sh` for stable releases

- Automatic rollback capabilities

- Comprehensive reporting and logging

## Monitoring and Alerting

### Metrics Collection

- Deployment success/failure rates

- Health check response times

- Service availability metrics

- Resource utilization tracking

### Alert Integrations

- Webhook notifications for failures

- Slack/Teams integration support

- Custom alert routing based on severity

## Security Considerations

1. **RBAC**: Scripts respect Kubernetes RBAC permissions

2. **Service Accounts**: Use dedicated service accounts per component

3. **Secrets Management**: Secure handling of sensitive configuration

4. **Network Policies**: Respect cluster network security policies

## Troubleshooting

### Common Issues

1. **Permission Denied**

   ```bash

   chmod +x scripts/deployment/*.sh
   ```

2. **Namespace Not Found**

   ```bash

   kubectl create namespace neuronews
   ```

3. **Image Pull Errors**

   - Verify registry credentials

   - Check image tag existence

   - Validate network connectivity

4. **Health Check Failures**

   - Check service endpoints

   - Verify pod readiness

   - Review application logs

### Debug Mode

All scripts support verbose logging:

```bash

./deploy-canary.sh --service api --image-tag debug --verbose

```text

## Best Practices

1. **Always use dry-run first** for new deployments

2. **Monitor health checks** during deployments

3. **Keep rollback capability ready** for production changes

4. **Use staging environment** for validation

5. **Document deployment reasons** for audit trails

## Support and Maintenance

For issues, feature requests, or contributions:

1. Check existing GitHub issues

2. Review deployment logs

3. Validate environment prerequisites

4. Submit detailed bug reports with reproduction steps

