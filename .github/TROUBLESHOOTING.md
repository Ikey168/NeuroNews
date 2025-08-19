# CI/CD Troubleshooting Guide

This guide helps resolve common issues with the NeuroNews CI/CD pipeline.

## Quick Fixes for Common Errors

### 1. Connection Refused Errors

**Error**: `connection refused to localhost:8080`
```
error: unable to read URL "http://localhost:8080/openapi/v2"
```

**Cause**: Workflow trying to connect to Kubernetes API server that doesn't exist in CI environment.

**Fix**: Already resolved in latest workflows. If you see this error:
- Pull latest changes from the `78-kubernetes-cicd` branch
- The workflows now use client-side validation and proper connectivity checks

### 2. Artifact Upload Deprecation

**Error**: `uses a deprecated version of actions/upload-artifact: v3`

**Fix**: Already resolved. All workflows now use `actions/upload-artifact@v4`.

### 3. Missing Secrets

**Error**: `Error: secret "KUBE_CONFIG_STAGING" not found`

**Fix**: Add required secrets to repository:
```bash
# Get your kubeconfig
kubectl config view --raw > kubeconfig.yaml

# Encode it
base64 -i kubeconfig.yaml | tr -d '\n'

# Add to GitHub: Settings → Secrets → Actions → New repository secret
```

Required secrets:
- `KUBE_CONFIG_STAGING` - Staging cluster kubeconfig (base64 encoded)
- `KUBE_CONFIG_PRODUCTION` - Production cluster kubeconfig (base64 encoded)
- `GHCR_TOKEN` - GitHub Container Registry token
- `SLACK_WEBHOOK_URL` - Slack webhook for notifications (optional)

### 4. Tool Installation Failures

**Error**: `kubeval: command not found`

**Fix**: Workflows now include fallback behavior. If tools fail to install, validation continues with warnings. You can also run validation locally:

```bash
# Install kubeval
curl -L https://github.com/instrumenta/kubeval/releases/latest/download/kubeval-linux-amd64.tar.gz | tar xz
sudo mv kubeval /usr/local/bin

# Validate manifests
kubeval k8s/**/*.yaml
```

### 5. Permission Denied in Cluster

**Error**: `forbidden: User cannot create resource "deployments"`

**Fix**: Ensure service account has proper RBAC permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: neuronews-deployer
  namespace: neuronews
subjects:
- kind: ServiceAccount
  name: neuronews-deployer
  namespace: neuronews
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
```

## Workflow-Specific Issues

### PR Validation Workflow

**Issue**: Tests failing on specific components
**Check**: 
1. Look at the "Detect Changes" job to see which components were detected
2. Check component-specific test logs
3. Verify test files exist and are executable

**Issue**: Security scan failures
**Check**:
1. Review Bandit security report in artifacts
2. Fix security issues or add `# nosec` comments for false positives
3. Ensure Trivy container scan passes

### Canary Deployment Workflow

**Issue**: Cannot trigger manually
**Check**:
1. Go to Actions → Canary Deployment → Run workflow
2. Ensure you have write permissions to the repository
3. Check that required parameters are provided

**Issue**: Health checks failing
**Check**:
1. Verify service endpoints are responding
2. Check pod readiness and liveness probes
3. Review deployment logs for startup issues

### CI/CD Pipeline Workflow

**Issue**: Deployment skipped
**Expected**: Deployment only runs on `main` or `develop` branches with proper secrets
**Check**:
1. Verify branch name is correct
2. Confirm secrets are available
3. Check cluster connectivity test results

**Issue**: Container build failures
**Check**:
1. Verify Dockerfile syntax
2. Check for missing dependencies
3. Review build logs for specific errors

## Environment-Specific Issues

### Local Development

**Issue**: Cannot run deployment scripts locally
**Fix**:
```bash
# Make scripts executable
chmod +x scripts/deployment/*.sh

# Install required tools
sudo apt-get update
sudo apt-get install -y kubectl

# Configure kubectl
kubectl config set-cluster local --server=https://your-cluster-endpoint
kubectl config set-credentials user --token=your-token
kubectl config set-context local --cluster=local --user=user
kubectl config use-context local
```

### Staging Environment

**Issue**: Resources not found
**Check**:
1. Verify namespace exists: `kubectl get namespace neuronews-staging`
2. Check resource quotas: `kubectl describe quota -n neuronews-staging`
3. Verify RBAC permissions

### Production Environment

**Issue**: Canary deployment stuck
**Fix**:
```bash
# Check rollout status
kubectl rollout status deployment/neuronews-api -n neuronews

# Manual promotion if needed
kubectl argo rollouts promote neuronews-api -n neuronews

# Emergency rollback
kubectl argo rollouts abort neuronews-api -n neuronews
kubectl rollout undo deployment/neuronews-api -n neuronews
```

## Debug Commands

### Check Workflow Status
```bash
# Using GitHub CLI
gh run list --workflow="PR Validation Pipeline"
gh run view <run-id> --log

# Check specific job
gh run view <run-id> --job="k8s-validation"
```

### Validate Manifests Locally
```bash
# Client-side validation
kubectl apply --dry-run=client -f k8s/

# With kubeval
kubeval k8s/**/*.yaml

# With kustomize
kustomize build k8s/overlays/staging | kubectl apply --dry-run=client -f -
```

### Test Deployment Scripts
```bash
# Dry run canary deployment
./scripts/deployment/deploy-canary.sh --service api --image-tag test --dry-run

# Health check all services
./scripts/deployment/health-check.sh --service all

# Check rollback options
./scripts/deployment/rollback.sh --list-revisions --service api
```

### Check Cluster Resources
```bash
# Pod status
kubectl get pods -n neuronews --show-labels

# Deployment status
kubectl get deployments -n neuronews

# Events
kubectl get events -n neuronews --sort-by='.lastTimestamp'

# Resource usage
kubectl top pods -n neuronews
kubectl top nodes
```

## Performance Issues

### Slow Workflow Runs

**Causes & Fixes**:
1. **Large test suites**: Use matrix builds to parallelize tests
2. **Docker builds**: Use layer caching and multi-stage builds
3. **Tool downloads**: Cache tools between runs

**Optimization**:
```yaml
# Add caching to workflow
- name: Cache tools
  uses: actions/cache@v3
  with:
    path: /usr/local/bin
    key: tools-${{ runner.os }}-${{ hashFiles('scripts/install-tools.sh') }}
```

### High Resource Usage

**Check**:
1. Resource requests and limits in manifests
2. Node capacity and scheduling
3. Pod resource consumption

**Fix**:
```bash
# Adjust resource limits
kubectl patch deployment neuronews-api -n neuronews -p '{"spec":{"template":{"spec":{"containers":[{"name":"neuronews-api","resources":{"limits":{"memory":"512Mi","cpu":"500m"}}}]}}}}'
```

## Getting Help

### Escalation Path

1. **Check this guide** - Common issues and solutions
2. **Review workflow logs** - Specific error messages and context
3. **Test locally** - Reproduce issue in local environment
4. **Create issue** - Include logs, environment details, and reproduction steps

### Information to Include

When reporting issues, include:
- Workflow run URL
- Full error message
- Branch and commit SHA
- Environment (staging/production)
- Steps to reproduce
- Expected vs actual behavior

### Useful Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Argo Rollouts Documentation](https://argoproj.github.io/argo-rollouts/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)

## Prevention

### Best Practices

1. **Test locally first** - Validate changes before pushing
2. **Use feature branches** - Isolate changes and test in PRs
3. **Monitor regularly** - Set up alerts for workflow failures
4. **Keep updated** - Regularly update dependencies and tools
5. **Document changes** - Update documentation when modifying workflows

### Health Checks

Regular maintenance tasks:
- [ ] Rotate secrets monthly
- [ ] Update action versions quarterly
- [ ] Review and clean up old workflow runs
- [ ] Test disaster recovery procedures
- [ ] Validate backup and restore processes
