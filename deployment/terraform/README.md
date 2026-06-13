# NeuroNews Infrastructure

This directory contains Terraform configurations for the NeuroNews infrastructure.

## Components

- VPC and Networking (networking.tf)

- Neptune Graph Database (neptune.tf)

- S3 Storage (s3.tf)

- IAM Roles and Policies (iam.tf)

- Lambda Functions (lambda.tf)

- Analytics infrastructure (uses managed Snowflake service)

## Neptune Graph Database Setup

The Neptune cluster is configured with:

- High availability across multiple AZs

- VPC endpoints for secure access

- IAM authentication

- Automated backups

- Network ACLs and security groups for enhanced security

### Prerequisites

1. AWS credentials configured with appropriate permissions

2. Terraform >= 1.0

3. AWS CLI

### Configuration

1. Copy `terraform.tfvars.example` to `terraform.tfvars`:

```bash

cp terraform.tfvars.example terraform.tfvars

```text

2. Update the variables in `terraform.tfvars` to match your requirements:

```hcl

# Networking

vpc_cidr = "10.0.0.0/16"
availability_zones = ["us-west-2a", "us-west-2b"]

# Neptune Configuration

neptune_instance_class = "db.t3.medium"  # or larger for production

neptune_cluster_size = 1  # increase for high availability

neptune_port = 8182

```text

### Security Groups and Network Access

The Neptune cluster is deployed in private subnets with the following security measures:

- Network ACLs controlling inbound/outbound traffic

- Security groups limiting access to the Neptune port (8182)

- VPC endpoints for secure AWS service access

- Private subnets with NAT gateway for outbound internet access

### Deployment

1. Initialize Terraform:

```bash

terraform init

```text

2. Review the plan:

```bash

terraform plan

```text

3. Apply the configuration:

```bash

terraform apply

```text

### Accessing Neptune

After deployment, you can access Neptune through:

1. The Neptune endpoint (available in Terraform outputs)

2. AWS CLI using IAM authentication

3. Application code using the Neptune driver

Example connection string will be provided in the Terraform outputs:

```text

neptune_cluster_endpoint = "your-cluster.cluster-xxxxxx.region.neptune.amazonaws.com"
neptune_cluster_port = 8182

```text

### Backup and Maintenance

- Automated backups are configured with a retention period of 7 days

- Maintenance window is set to "03:00-04:00" UTC

- Audit logs can be enabled by setting `neptune_enable_audit_logs = true`

### Cost Optimization

For development environments:

- Use `db.t3.medium` instance class

- Set `neptune_cluster_size = 1` (no replicas)

- Enable `neptune_skip_final_snapshot = true`

For production environments:

- Use appropriate instance class based on workload

- Set `neptune_cluster_size >= 2` for high availability

- Configure longer backup retention period

- Enable audit logs

- Set `neptune_skip_final_snapshot = false`

## Support

For issues and support:

1. Check AWS Neptune documentation

2. Review CloudWatch logs

3. Check security group and NACL rules if connectivity issues arise

