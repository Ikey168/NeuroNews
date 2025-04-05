# Outputs for NeuroNews Terraform configuration

# S3 Bucket outputs
output "raw_articles_bucket_name" {
  description = "Name of the S3 bucket for raw articles"
  value       = aws_s3_bucket.raw_articles.bucket
}

output "raw_articles_bucket_arn" {
  description = "ARN of the S3 bucket for raw articles"
  value       = aws_s3_bucket.raw_articles.arn
}

output "raw_articles_bucket_region" {
  description = "Region of the S3 bucket for raw articles"
  value       = var.aws_region
}

# Redshift outputs
output "redshift_cluster_id" {
  description = "ID of the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.id
}

output "redshift_cluster_endpoint" {
  description = "Endpoint of the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.endpoint
}

output "redshift_database_name" {
  description = "Name of the database in the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.database_name
}

output "redshift_port" {
  description = "Port of the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.port
}

output "redshift_iam_role_arn" {
  description = "ARN of the IAM role for Redshift to access S3"
  value       = aws_iam_role.redshift_s3_access.arn
}

# General outputs
output "environment" {
  description = "Deployment environment"
  value       = var.environment
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}
