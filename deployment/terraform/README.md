# NeuroNews Terraform Configuration

This directory contains Terraform configuration for provisioning AWS infrastructure for the NeuroNews project.

## Resources

The following AWS resources are provisioned:

- **S3 Bucket**: For storing raw article/document data
  - Versioning enabled
  - Server-side encryption enabled
  - Public access blocked
  - Lifecycle rules for archiving old data

- **Redshift Cluster**: For storing and analyzing processed texts
  - Encrypted storage
  - Enhanced VPC routing
  - Private access only (not publicly accessible)
  - Automated snapshots
  - IAM role for S3 access
  - Security group with restricted access
  - Parameter group with SSL required

- **Neptune Cluster**: For storing and querying knowledge graphs
  - Graph database optimized for relationship data
  - Encrypted storage
  - IAM authentication enabled
  - CloudWatch logs for auditing
  - Automated backups
  - S3 bucket for bulk loading data
  - Security group with restricted access

- **Lambda Functions**: For serverless processing
  - Article processor: Processes raw articles and stores results in Redshift
  - Knowledge graph generator: Generates knowledge graphs from processed articles
  - Article notifier: Sends notifications when new articles are available
  - S3 bucket for Lambda function code
  - IAM role with appropriate permissions
  - CloudWatch logs for monitoring
  - Event-driven triggers (S3 events, CloudWatch scheduled events)

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
| redshift_cluster_identifier | Identifier for the Redshift cluster | neuronews-redshift |
| redshift_database_name | Name of the database in the Redshift cluster | neuronews |
| redshift_master_username | Master username for the Redshift cluster | neuronews_admin |
| redshift_master_password | Master password for the Redshift cluster | ChangeMe123! (should be overridden) |
| redshift_node_type | Node type for the Redshift cluster | dc2.large |
| redshift_cluster_type | Cluster type (single-node or multi-node) | single-node |
| redshift_number_of_nodes | Number of nodes in the Redshift cluster | 1 |
| redshift_skip_final_snapshot | Whether to skip the final snapshot | true (false in prod) |
| neptune_cluster_identifier | Identifier for the Neptune cluster | neuronews-neptune |
| neptune_instance_class | Instance class for the Neptune cluster | db.t3.medium |
| neptune_instance_count | Number of instances in the Neptune cluster | 1 |
| neptune_master_username | Master username for the Neptune cluster | neptune_admin |
| neptune_master_password | Master password for the Neptune cluster | ChangeMe456! (should be overridden) |
| neptune_port | Port for the Neptune cluster | 8182 |
| neptune_preferred_backup_window | Preferred backup window for the Neptune cluster | 02:00-03:00 |
| neptune_backup_retention_period | Backup retention period in days | 7 |
| neptune_skip_final_snapshot | Whether to skip the final snapshot | true (false in prod) |
| neptune_apply_immediately | Whether to apply changes immediately | true (false in prod) |
| lambda_function_prefix | Prefix for Lambda function names | neuronews |
| lambda_runtime | Runtime for Lambda functions | python3.9 |
| lambda_timeout | Timeout for Lambda functions in seconds | 300 (5 minutes) |
| lambda_memory_size | Memory size for Lambda functions in MB | 512 |
| lambda_concurrent_executions | Maximum concurrent executions | 10 |
| lambda_log_retention_days | Number of days to retain Lambda logs | 14 |
| lambda_s3_key_prefix | Prefix for Lambda function code in S3 | lambda-functions |

## Outputs

| Name | Description |
|------|-------------|
| raw_articles_bucket_name | Name of the S3 bucket for raw articles |
| raw_articles_bucket_arn | ARN of the S3 bucket for raw articles |
| raw_articles_bucket_region | Region of the S3 bucket for raw articles |
| redshift_cluster_id | ID of the Redshift cluster |
| redshift_cluster_endpoint | Endpoint of the Redshift cluster |
| redshift_database_name | Name of the database in the Redshift cluster |
| redshift_port | Port of the Redshift cluster |
| redshift_iam_role_arn | ARN of the IAM role for Redshift to access S3 |
| neptune_cluster_id | ID of the Neptune cluster |
| neptune_cluster_endpoint | Writer endpoint of the Neptune cluster |
| neptune_reader_endpoint | Reader endpoint of the Neptune cluster |
| neptune_port | Port of the Neptune cluster |
| neptune_iam_role_arn | ARN of the IAM role for Neptune to access S3 |
| neptune_load_bucket_name | Name of the S3 bucket for Neptune bulk load data |
| neptune_load_bucket_arn | ARN of the S3 bucket for Neptune bulk load data |
| lambda_code_bucket_name | Name of the S3 bucket for Lambda function code |
| lambda_code_bucket_arn | ARN of the S3 bucket for Lambda function code |
| lambda_execution_role_arn | ARN of the IAM role for Lambda functions |
| article_processor_function_name | Name of the article processor Lambda function |
| article_processor_function_arn | ARN of the article processor Lambda function |
| knowledge_graph_generator_function_name | Name of the knowledge graph generator Lambda function |
| knowledge_graph_generator_function_arn | ARN of the knowledge graph generator Lambda function |
| article_notifier_function_name | Name of the article notifier Lambda function |
| article_notifier_function_arn | ARN of the article notifier Lambda function |
| environment | Deployment environment |
| region | AWS region |
