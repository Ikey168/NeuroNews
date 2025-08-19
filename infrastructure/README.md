# NeuroNews Infrastructure

This directory contains infrastructure as code (IaC) templates for deploying NeuroNews components.

## Structure

```
infrastructure/
├── terraform/          # Terraform modules for AWS infrastructure
├── helm/               # Helm charts for Kubernetes deployments
├── cloudformation/     # CloudFormation templates
└── scripts/           # Deployment and management scripts
```

## Terraform Modules

- `terraform/eks/` - EKS cluster configuration
- `terraform/rds/` - RDS PostgreSQL setup
- `terraform/elasticache/` - Redis cluster configuration
- `terraform/s3/` - S3 buckets for data storage
- `terraform/vpc/` - Network infrastructure

## Helm Charts

- `helm/neuronews/` - Main application chart
- `helm/monitoring/` - Prometheus and Grafana stack
- `helm/ingress/` - NGINX ingress controller

## Deployment

```bash
# Initialize Terraform
cd terraform
terraform init
terraform plan
terraform apply

# Deploy with Helm
helm install neuronews ./helm/neuronews/
```

## Environment Management

- Development: `dev/`
- Staging: `staging/`
- Production: `prod/`

Each environment has its own configuration files and variable definitions.
