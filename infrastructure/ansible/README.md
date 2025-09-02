# NeuroNews Infrastructure Automation

Complete Ansible automation for provisioning and deploying the NeuroNews application infrastructure on AWS or GCP.

## Overview

This Ansible automation provides:
- **Cloud Infrastructure Provisioning**: Automated setup of VPC, security groups, and compute instances
- **Kubernetes Cluster Deployment**: Full K8s cluster with master and worker nodes
- **Application Deployment**: FastAPI, NLP services, scrapers, and supporting infrastructure
- **End-to-End Testing**: Comprehensive validation of the complete deployment

## Features

### 🚀 Infrastructure Provisioning
- **Multi-Cloud Support**: AWS EC2 and Google Cloud Platform
- **Network Configuration**: VPC, subnets, security groups, and load balancers
- **Auto-Scaling**: Configurable instance types and scaling groups
- **Security**: Comprehensive firewall rules and security group configurations

### 🎯 Kubernetes Automation
- **Cluster Setup**: Multi-master HA configuration with worker nodes
- **CNI**: Calico network plugin for pod networking
- **Ingress**: NGINX ingress controller with SSL termination
- **Storage**: Dynamic persistent volume provisioning
- **Monitoring**: MetalLB load balancer and cert-manager for SSL

### 📦 Application Deployment
- **Database**: PostgreSQL with persistent storage
- **Cache**: Redis cluster for application caching
- **API**: FastAPI application with health checks
- **Processing**: NLP services and news scrapers
- **Reverse Proxy**: NGINX with SSL/TLS termination

### 🔍 Testing & Validation
- **Connectivity Tests**: Database, cache, and API endpoint validation
- **Performance Tests**: Load testing and response time validation
- **Security Tests**: RBAC, network policies, and security contexts
- **End-to-End Tests**: Complete workflow validation

## Prerequisites

### System Requirements
```bash
# Python 3.8+
python3 --version

# Ansible 2.14+
ansible --version

# Required collections
ansible-galaxy collection install kubernetes.core
ansible-galaxy collection install amazon.aws
ansible-galaxy collection install google.cloud
```

### Cloud Provider Setup

#### AWS Configuration
```bash
# Install AWS CLI
pip install awscli

# Configure credentials
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region name: us-east-1
# Default output format: json

# Create SSH key pair
aws ec2 create-key-pair --key-name neuronews-key --query 'KeyMaterial' --output text > ~/.ssh/neuronews-key.pem
chmod 400 ~/.ssh/neuronews-key.pem
```

#### GCP Configuration
```bash
# Install Google Cloud SDK
curl https://sdk.cloud.google.com | bash
gcloud init

# Authenticate
gcloud auth application-default login

# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable compute.googleapis.com
gcloud services enable container.googleapis.com

# Create SSH key
ssh-keygen -t rsa -f ~/.ssh/neuronews-gcp-key
```

## Quick Start

### 1. Basic Deployment (AWS)
```bash
# Clone repository
git clone https://github.com/Ikey168/NeuroNews.git
cd NeuroNews/ansible

# Deploy complete infrastructure
ansible-playbook provision-infrastructure.yml \
  -e "provider=aws" \
  -e "region=us-east-1" \
  -e "deployment_env=production"
```

### 2. Basic Deployment (GCP)
```bash
# Deploy to Google Cloud
ansible-playbook provision-infrastructure.yml \
  -e "provider=gcp" \
  -e "region=us-central1" \
  -e "gcp_project=your-project-id" \
  -e "deployment_env=production"
```

### 3. End-to-End Testing
```bash
# Run complete test suite
ansible-playbook test-deployment.yml \
  -e "provider=aws" \
  -e "test_env=staging" \
  -e "cleanup=true"
```

## Configuration

### Inventory Management
```yaml
# inventories/hosts.yml
all:
  children:
    kubernetes:
      children:
        masters:
          hosts:
            k8s-master-1:
              ansible_host: 10.0.1.10
        workers:
          hosts:
            k8s-worker-1:
              ansible_host: 10.0.1.20
```

### Environment Variables
```yaml
# group_vars/all.yml
app:
  name: "neuronews"
  version: "latest"
  namespace: "neuronews"
  environment: "production"

kubernetes_version: "1.28.0"
docker_version: "24.0"
```

### AWS-Specific Configuration
```yaml
# group_vars/aws.yml
aws:
  region: "us-east-1"
  instance_type_master: "t3.medium"
  instance_type_worker: "t3.large"
  key_name: "neuronews-key"
  vpc_cidr: "10.0.0.0/16"
```

### GCP-Specific Configuration
```yaml
# group_vars/gcp.yml
gcp:
  project: "your-project-id"
  machine_type_master: "e2-standard-2"
  machine_type_worker: "e2-standard-4"
  zone: "us-central1-a"
  network_cidr: "10.0.0.0/16"
```

## Playbook Reference

### Core Playbooks

#### `provision-infrastructure.yml`
Complete infrastructure provisioning and application deployment.

**Parameters:**
- `provider`: Cloud provider (`aws` or `gcp`)
- `region`: Target region for deployment
- `state`: Infrastructure state (`present` or `absent`)
- `deployment_env`: Environment name (`production`, `staging`, `development`)

**Example:**
```bash
ansible-playbook provision-infrastructure.yml \
  -e "provider=aws" \
  -e "region=us-west-2" \
  -e "deployment_env=staging"
```

#### `test-deployment.yml`
End-to-end testing and validation.

**Parameters:**
- `provider`: Cloud provider for testing
- `test_env`: Test environment name
- `cleanup`: Cleanup resources after testing (`true`/`false`)

**Example:**
```bash
ansible-playbook test-deployment.yml \
  -e "provider=gcp" \
  -e "test_env=testing" \
  -e "cleanup=false"
```

### Task Modules

#### Infrastructure Tasks
- `tasks/provision-aws.yml`: AWS infrastructure provisioning
- `tasks/provision-gcp.yml`: GCP infrastructure provisioning

#### Installation Tasks
- `tasks/install-docker.yml`: Docker CE installation and configuration
- `tasks/install-kubernetes.yml`: Kubernetes components installation

#### Cluster Tasks
- `tasks/init-kubernetes-cluster.yml`: Kubernetes cluster initialization
- `tasks/join-kubernetes-workers.yml`: Worker node joining

#### Application Tasks
- `tasks/deploy-applications.yml`: NeuroNews application deployment
- `tasks/validate-deployment.yml`: Deployment validation and testing

## Advanced Usage

### Custom Configuration

#### Override Default Settings
```bash
# Custom instance types
ansible-playbook provision-infrastructure.yml \
  -e "provider=aws" \
  -e "master_instance_type=t3.large" \
  -e "worker_instance_type=t3.xlarge"

# Custom Kubernetes version
ansible-playbook provision-infrastructure.yml \
  -e "kubernetes_version=1.29.0"

# Custom application settings
ansible-playbook provision-infrastructure.yml \
  -e "app_replicas=5" \
  -e "enable_autoscaling=true"
```

#### Environment-Specific Deployments
```bash
# Development environment
ansible-playbook provision-infrastructure.yml \
  -e "deployment_env=development" \
  -e "node_count=1" \
  -e "instance_type=t3.small"

# Production environment
ansible-playbook provision-infrastructure.yml \
  -e "deployment_env=production" \
  -e "node_count=6" \
  -e "enable_monitoring=true" \
  -e "enable_backup=true"
```

### Scaling Operations

#### Add Worker Nodes
```bash
# Scale up worker nodes
ansible-playbook provision-infrastructure.yml \
  -e "provider=aws" \
  -e "worker_count=5" \
  -e "state=present" \
  --tags "workers"
```

#### Update Applications
```bash
# Update application version
ansible-playbook provision-infrastructure.yml \
  -e "app_version=v2.0.0" \
  --tags "deploy"
```

### Maintenance Operations

#### Cluster Upgrades
```bash
# Upgrade Kubernetes version
ansible-playbook provision-infrastructure.yml \
  -e "kubernetes_version=1.29.0" \
  --tags "kubernetes"
```

#### Security Updates
```bash
# Apply security updates
ansible-playbook provision-infrastructure.yml \
  --tags "security,updates"
```

## Monitoring and Troubleshooting

### Health Checks
```bash
# Check cluster status
kubectl get nodes
kubectl get pods -n neuronews

# Check application health
kubectl get svc -n neuronews
curl http://LOAD_BALANCER_IP/health
```

### Common Issues

#### SSH Connection Issues
```bash
# Verify SSH key permissions
chmod 400 ~/.ssh/neuronews-key.pem

# Test SSH connection
ssh -i ~/.ssh/neuronews-key.pem ubuntu@NODE_IP

# Check security group rules
aws ec2 describe-security-groups --group-ids sg-xxxxxxxx
```

#### Kubernetes Issues
```bash
# Check cluster logs
journalctl -u kubelet -f

# Reset cluster (if needed)
kubeadm reset
```

#### Application Issues
```bash
# Check pod logs
kubectl logs -n neuronews -l app=fastapi

# Check service endpoints
kubectl get endpoints -n neuronews

# Verify persistent volumes
kubectl get pv,pvc -n neuronews
```

### Log Analysis
```bash
# Application logs
kubectl logs -n neuronews deployment/fastapi-deployment -f

# System logs
journalctl -u docker -f
journalctl -u kubelet -f

# Ansible logs
ansible-playbook provision-infrastructure.yml -v
```

## Security Best Practices

### Access Control
- Use IAM roles and service accounts
- Implement RBAC for Kubernetes
- Rotate SSH keys regularly
- Enable audit logging

### Network Security
- Configure security groups/firewall rules
- Use network policies in Kubernetes
- Enable TLS/SSL for all communications
- Implement VPC peering for multi-region

### Data Security
- Encrypt data at rest and in transit
- Use Kubernetes secrets for sensitive data
- Implement backup and disaster recovery
- Regular security scanning

## Performance Optimization

### Resource Allocation
```yaml
# Optimized resource requests
resources:
  requests:
    cpu: "200m"
    memory: "256Mi"
  limits:
    cpu: "1000m"
    memory: "1Gi"
```

### Auto-Scaling
```yaml
# Horizontal Pod Autoscaler
autoscaling:
  enabled: true
  min_replicas: 3
  max_replicas: 10
  target_cpu_utilization: 70
```

### Storage Optimization
```yaml
# High-performance storage
storageClassName: "gp3"
volumeSize: "100Gi"
iops: 3000
```

## Cost Optimization

### Resource Management
- Use spot instances for non-critical workloads
- Implement cluster autoscaling
- Schedule resource-intensive jobs during off-peak hours
- Regular cleanup of unused resources

### Instance Optimization
```bash
# Use appropriate instance types
t3.micro     # Development
t3.small     # Testing
t3.medium    # Staging
t3.large     # Production workers
t3.xlarge    # Production masters
```

## Backup and Disaster Recovery

### Automated Backups
```bash
# Database backups
kubectl create cronjob postgres-backup \
  --image=postgres:15-alpine \
  --schedule="0 2 * * *" \
  -- pg_dump -h postgres-service -U neuronews neuronews > /backup/db-$(date +%Y%m%d).sql

# Configuration backups
kubectl get all -n neuronews -o yaml > neuronews-backup.yaml
```

### Disaster Recovery
```bash
# Restore from backup
kubectl apply -f neuronews-backup.yaml

# Restore database
kubectl exec -it postgres-pod -- psql -U neuronews neuronews < db-backup.sql
```

## Contributing

### Development Setup
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run syntax checks
ansible-lint playbooks/
yamllint .

# Test in development environment
ansible-playbook test-deployment.yml -e "test_env=development"
```

### Testing
```bash
# Run unit tests
molecule test

# Integration testing
ansible-playbook test-deployment.yml --check

# Validation testing
ansible-playbook provision-infrastructure.yml --syntax-check
```

## Support and Documentation

### Additional Resources
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Ansible Documentation](https://docs.ansible.com/)
- [AWS Documentation](https://docs.aws.amazon.com/)
- [GCP Documentation](https://cloud.google.com/docs/)

### Community
- GitHub Issues: Report bugs and feature requests
- Discussions: Community support and questions
- Wiki: Additional documentation and examples

---

**Last Updated**: {{ ansible_date_time.date }}
**Version**: 1.0.0
**Maintainer**: NeuroNews DevOps Team
