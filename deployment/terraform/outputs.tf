# Outputs for NeuroNews Terraform configuration

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

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}
