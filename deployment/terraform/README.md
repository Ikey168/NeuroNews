# NeuroNews Terraform Configuration

This directory contains Terraform configuration for provisioning AWS infrastructure for the NeuroNews project.

## Resources

The following AWS resources are provisioned:

- **S3 Bucket**: For storing raw article/document data
  - Versioning enabled
  - Server-side encryption enabled
  - Public access blocked
  - Lifecycle rules for archiving old data

## Usage

### Prerequisites

- [Terraform](https://www.terraform.io/downloads.html) (v1.0.0+)
- AWS credentials configured (via AWS CLI, environment variables, or other methods)

### Commands

Initialize Terraform:

```bash
terraform init
```

Plan the deployment:

```bash
terraform plan -var="environment=dev"
```

Apply the configuration:

```bash
terraform apply -var="environment=dev"
```

Destroy the infrastructure:

```bash
terraform destroy -var="environment=dev"
```

## Variables

| Name | Description | Default |
|------|-------------|---------|
| aws_region | AWS region to deploy resources | us-east-1 |
| environment | Deployment environment (dev, staging, prod) | dev |
| bucket_name_prefix | Prefix for the S3 bucket name | neuronews |
| tags | Common tags to apply to all resources | Project = "NeuroNews", ManagedBy = "Terraform" |

## Outputs

| Name | Description |
|------|-------------|
| raw_articles_bucket_name | Name of the S3 bucket for raw articles |
| raw_articles_bucket_arn | ARN of the S3 bucket for raw articles |
| raw_articles_bucket_region | Region of the S3 bucket for raw articles |
| environment | Deployment environment |
