# GitHub Actions Workflows Documentation

This document explains the GitHub Actions workflows in the NeuroNews repository and their requirements.

## Workflows Overview

### 1. PR Validation Pipeline (`pr-validation.yml`)

**Purpose**: Validates pull requests with comprehensive testing and validation

**Triggers**: 
- Pull requests to `main` branch
- PR events: opened, synchronize, reopened

**Features**:
- **Change Detection**: Uses path filters to detect which components changed
- **Security Scanning**: Bandit security analysis with artifact upload
- **Kubernetes Validation**: Multiple validation tools (kubeval, kustomize, helm)
- **Unit Testing**: Component-specific testing with coverage reporting
- **Integration Testing**: Cross-component integration validation
- **Performance Testing**: Load testing and performance metrics
- **Code Quality**: Linting, type checking, and quality gates

**Requirements**:
- No external cluster required (uses client-side validation)
- Automatically installs required validation tools
- Graceful fallbacks if tools fail to install

### 2. Canary Deployment Pipeline (`canary-deployment.yml`)

**Purpose**: Manual canary deployments with progressive traffic management

**Triggers**: 
- Manual workflow dispatch only
- Requires manual approval for production deployments

**Parameters**:
- `service`: Which service to deploy (api, dashboard, scraper, nlp-processor, all)
- `image_tag`: Container image tag to deploy
- `traffic_percentage`: Initial canary traffic percentage (10-100)
- `auto_promote`: Whether to automatically promote successful canaries
- `environment`: Target environment (staging, production)

**Requirements**:
- **Kubernetes Cluster Access**: Requires valid kubeconfig
- **Secrets Required**:
  - `KUBE_CONFIG_STAGING`: Staging cluster kubeconfig
  - `KUBE_CONFIG_PRODUCTION`: Production cluster kubeconfig
  - `SLACK_WEBHOOK_URL`: For deployment notifications
- **Tools Required**: kubectl, argo-rollouts CLI

### 3. CI/CD Pipeline (`ci-cd-pipeline.yml`)

**Purpose**: Automated testing and deployment pipeline

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests for testing only

**Features**:
- **Automated Testing**: Full test suite execution
- **Container Building**: Multi-architecture container builds
- **Staging Deployment**: Automatic deployment to staging (develop branch)
- **Production Deployment**: Automatic deployment to production (main branch)
- **Cluster Connectivity Checks**: Validates cluster access before deployment

**Requirements**:
- **For Testing**: No external dependencies
- **For Deployment**: 
  - Valid cluster access via kubeconfig secrets
  - Container registry credentials
  - Proper RBAC permissions in target clusters

## Secrets Configuration

### Required Repository Secrets

#### Container Registry
```
GHCR_TOKEN=<GitHub Container Registry token>
```

#### Kubernetes Clusters
```
KUBE_CONFIG_STAGING=<Base64 encoded kubeconfig for staging>
KUBE_CONFIG_PRODUCTION=<Base64 encoded kubeconfig for production>
```

#### Notifications
```
SLACK_WEBHOOK_URL=<Slack webhook for deployment notifications>
```

#### API Keys (for applications)
```
OPENAI_API_KEY=<OpenAI API key for NLP processing>
NEWS_API_KEY=<News API key for scraping>
```

### Setting Up Kubeconfig Secrets

1. **Get your kubeconfig**:
   ```bash
   kubectl config view --raw > kubeconfig.yaml
   ```

2. **Base64 encode it**:
   ```bash
   base64 -i kubeconfig.yaml | tr -d '\n'
   ```

3. **Add to GitHub Secrets**:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Add new secret with the base64 encoded content

## Workflow Behavior

### PR Validation
- ✅ **Always runs**: Validation steps that don't require external services
- ⚠️ **Conditional**: Deployment steps only run if secrets are available
- 🔄 **Fallback**: If validation tools fail to install, workflow continues with warnings

### Canary Deployment
- 🚫 **Manual only**: Never runs automatically
- ✅ **Cluster required**: Will fail if cluster access is not available
- 📊 **Monitoring**: Includes health checks and automated rollback

### CI/CD Pipeline
- ✅ **Testing**: Always runs tests and validation
- ⚠️ **Deployment**: Only attempts deployment if:
  - Branch is `main` or `develop`
  - Required secrets are available
  - Cluster connectivity is confirmed

## Troubleshooting

### Common Issues

#### 1. "Connection refused" errors
**Cause**: Workflow trying to connect to Kubernetes API without cluster access
**Solution**: Workflows are now updated to use client-side validation and check connectivity before deployment

#### 2. "Secret not found" errors
**Cause**: Missing required secrets for deployment
**Solution**: Ensure all required secrets are configured in repository settings

#### 3. "Permission denied" errors
**Cause**: Insufficient RBAC permissions in target cluster
**Solution**: Ensure service account has proper permissions for the namespace

#### 4. Artifact upload failures
**Cause**: Using deprecated artifact actions
**Solution**: Updated to use `actions/upload-artifact@v4`

### Debug Steps

1. **Check workflow logs**: Review the specific step that's failing
2. **Verify secrets**: Ensure all required secrets are set in repository settings
3. **Test cluster access**: Manually test kubectl commands with the same kubeconfig
4. **Validate manifests locally**: Use kubectl or kubeval to validate manifests before pushing

## Best Practices

### For Development
1. **Test locally first**: Validate manifests and scripts locally before pushing
2. **Use feature branches**: Create PRs for all changes to trigger validation
3. **Review artifacts**: Check uploaded test reports and security scans

### For Deployment
1. **Stage first**: Always deploy to staging before production
2. **Monitor health**: Use canary deployments for production changes
3. **Have rollback ready**: Ensure rollback procedures are tested

### For Maintenance
1. **Keep secrets updated**: Rotate kubeconfig and API keys regularly
2. **Monitor workflow runs**: Set up notifications for workflow failures
3. **Update dependencies**: Keep action versions and tools updated

## Security Considerations

1. **Secret Rotation**: Regularly rotate all API keys and kubeconfig files
2. **RBAC**: Use minimal required permissions for service accounts
3. **Network Policies**: Ensure proper network isolation in clusters
4. **Scan Results**: Review security scan results in artifacts
5. **Access Logs**: Monitor cluster access logs for unusual activity

## Support

For issues with workflows:
1. Check this documentation first
2. Review workflow run logs
3. Validate local setup matches CI requirements
4. Create issue with detailed error logs and reproduction steps
