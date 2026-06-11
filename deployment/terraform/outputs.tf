output "article_processor_function_arn" {
  description = "The ARN of the article processor Lambda function"
  value       = aws_lambda_function.article_processor.arn
}

output "article_notifier_function_arn" {
  description = "The ARN of the article notifier Lambda function"
  value       = aws_lambda_function.article_notifier.arn
}

output "knowledge_graph_generator_function_arn" {
  description = "The ARN of the knowledge graph generator Lambda function"
  value       = aws_lambda_function.knowledge_graph_generator.arn
}

output "cross_account_role_arn" {
  value       = ""
}

output "s3_bucket_name" {
  description = "The name of the raw articles S3 bucket"
  value       = module.s3.raw_articles_bucket_name
}

output "s3_bucket_arn" {
  description = "The ARN of the raw articles S3 bucket"
  value       = module.s3.raw_articles_bucket_arn
}

output "s3_bucket_id" {
  description = "The ID of the raw articles S3 bucket"
  value       = module.s3.raw_articles_bucket_id
}

# Snowflake outputs would go here when Snowflake infrastructure is defined
# Currently using managed Snowflake service outside of Terraform
