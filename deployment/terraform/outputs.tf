# Outputs for NeuroNews Terraform configuration

output "environment" {
  description = "Deployment environment (dev, staging, prod)"
  value       = var.environment
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

# Redshift outputs
output "redshift_cluster_id" {
  description = "Redshift cluster identifier"
  value       = aws_redshift_cluster.processed_texts.cluster_identifier
}

output "redshift_cluster_endpoint" {
  description = "Redshift cluster endpoint"
  value       = aws_redshift_cluster.processed_texts.endpoint
}

output "redshift_database_name" {
  description = "Redshift database name"
  value       = aws_redshift_cluster.processed_texts.database_name
}

output "redshift_port" {
  description = "Redshift port"
  value       = aws_redshift_cluster.processed_texts.port
}

output "redshift_iam_role_arn" {
  description = "Redshift IAM role ARN"
  value       = aws_iam_role.redshift_s3_access.arn
}

# Neptune outputs
output "neptune_cluster_id" {
  description = "Neptune cluster identifier"
  value       = aws_neptune_cluster.knowledge_graphs.cluster_identifier
}

output "neptune_cluster_endpoint" {
  description = "Neptune cluster endpoint"
  value       = aws_neptune_cluster.knowledge_graphs.endpoint
}

output "neptune_reader_endpoint" {
  description = "Neptune cluster reader endpoint"
  value       = aws_neptune_cluster.knowledge_graphs.reader_endpoint
}

output "neptune_port" {
  description = "Neptune port"
  value       = aws_neptune_cluster.knowledge_graphs.port
}

output "neptune_iam_role_arn" {
  description = "Neptune IAM role ARN"
  value       = aws_iam_role.neptune_s3_access.arn
}

# Lambda outputs
output "lambda_code_bucket_name" {
  description = "Name of the S3 bucket for Lambda code"
  value       = aws_s3_bucket.lambda_code.bucket
}

output "lambda_code_bucket_arn" {
  description = "ARN of the S3 bucket for Lambda code"
  value       = aws_s3_bucket.lambda_code.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution_role.arn
}

output "article_processor_function_name" {
  description = "Name of the article processor Lambda function"
  value       = aws_lambda_function.article_processor.function_name
}

output "article_processor_function_arn" {
  description = "ARN of the article processor Lambda function"
  value       = aws_lambda_function.article_processor.arn
}

output "knowledge_graph_generator_function_name" {
  description = "Name of the knowledge graph generator Lambda function"
  value       = aws_lambda_function.knowledge_graph_generator.function_name
}

output "knowledge_graph_generator_function_arn" {
  description = "ARN of the knowledge graph generator Lambda function"
  value       = aws_lambda_function.knowledge_graph_generator.arn
}

output "article_notifier_function_name" {
  description = "Name of the article notifier Lambda function"
  value       = aws_lambda_function.article_notifier.function_name
}

output "article_notifier_function_arn" {
  description = "ARN of the article notifier Lambda function"
  value       = aws_lambda_function.article_notifier.arn
}

# S3 outputs
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

output "neptune_load_bucket_name" {
  description = "Name of the S3 bucket for Neptune load data"
  value       = aws_s3_bucket.neptune_load.bucket
}

output "neptune_load_bucket_arn" {
  description = "ARN of the S3 bucket for Neptune load data"
  value       = aws_s3_bucket.neptune_load.arn
}

# IAM outputs
output "administrators_group_name" {
  description = "Name of the administrators group"
  value       = var.create_admin_group ? (length(aws_iam_group.administrators) > 0 ? aws_iam_group.administrators[0].name : "") : ""
}

output "developers_group_name" {
  description = "Name of the developers group"
  value       = var.create_developer_group ? (length(aws_iam_group.developers) > 0 ? aws_iam_group.developers[0].name : "") : ""
}

output "cicd_user_name" {
  description = "Name of the CI/CD user"
  value       = var.create_cicd_user ? (length(aws_iam_user.cicd_user) > 0 ? aws_iam_user.cicd_user[0].name : "") : ""
}

output "cicd_user_arn" {
  description = "ARN of the CI/CD user"
  value       = var.create_cicd_user ? (length(aws_iam_user.cicd_user) > 0 ? aws_iam_user.cicd_user[0].arn : "") : ""
}

output "ec2_role_arn" {
  description = "ARN of the EC2 role"
  value       = aws_iam_role.ec2_role.arn
}

output "ec2_instance_profile_name" {
  description = "Name of the EC2 instance profile"
  value       = aws_iam_instance_profile.ec2_profile.name
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS execution role"
  value       = aws_iam_role.ecs_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "cross_account_role_arn" {
  description = "ARN of the cross-account role"
  value       = var.create_cross_account_role && var.trusted_account_id != "" ? (length(aws_iam_role.cross_account_role) > 0 ? aws_iam_role.cross_account_role[0].arn : "") : ""
}
