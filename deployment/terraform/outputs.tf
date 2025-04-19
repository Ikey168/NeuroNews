<<<<<<< HEAD
output "article_processor_function_arn" {
  description = "The ARN of the article processor Lambda function."
  value       = aws_lambda_function.article_processor.arn
}

output "article_notifier_function_arn" {
  description = "The ARN of the article notifier Lambda function."
  value       = aws_lambda_function.article_notifier.arn
}

output "knowledge_graph_generator_function_arn" {
  description = "The ARN of the knowledge graph generator Lambda function."
  value       = aws_lambda_function.knowledge_graph_generator.arn
}

output "cross_account_role_arn" {
  description = "The ARN of the cross-account role."
  value       = var.create_cross_account_role ? (var.trusted_account_id != "" ? aws_iam_role.cross_account_role[0].arn : "") : ""
}

output "s3_bucket_name" {
  description = "The name of the raw articles S3 bucket."
  value       = module.s3.raw_articles_bucket_name
}

output "s3_bucket_arn" {
  description = "The ARN of the raw articles S3 bucket."
  value       = module.s3.raw_articles_bucket_arn
}

output "s3_bucket_id" {
  description = "The ID of the raw articles S3 bucket."
  value       = module.s3.raw_articles_bucket_id
}

output "redshift_cluster_endpoint" {
  description = "The connection endpoint for the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.endpoint
}

output "redshift_cluster_id" {
  description = "The ID of the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.id
}

output "redshift_cluster_database_name" {
  description = "The name of the default database in the Redshift cluster"
  value       = aws_redshift_cluster.processed_texts.database_name
}

output "redshift_cluster_port" {
  description = "The port the Redshift cluster accepts connections on"
  value       = aws_redshift_cluster.processed_texts.port
=======
output "lambda_function_names" {
  value = [
    aws_lambda_function.article_processor.function_name,
    aws_lambda_function.knowledge_graph_generator.function_name,
    aws_lambda_function.article_notifier.function_name,
  ]
  description = "Names of the deployed Lambda functions"
}

output "lambda_function_arns" {
  value = [
    aws_lambda_function.article_processor.arn,
    aws_lambda_function.knowledge_graph_generator.arn,
    aws_lambda_function.article_notifier.arn,
  ]
  description = "ARNs of the deployed Lambda functions"
}

output "lambda_execution_role_arn" {
  value       = aws_iam_role.lambda_execution_role.arn
  description = "ARN of the Lambda execution role"
}

output "ec2_instance_profile_id" {
  value       = aws_iam_instance_profile.ec2_profile.id
  description = "ID of the EC2 instance profile"
}

output "ec2_role_arn" {
  value       = aws_iam_role.ec2_role.arn
  description = "ARN of the EC2 role"
}

output "s3_bucket_name" {
  value       = module.s3.raw_articles_bucket_name
  description = "Name of the S3 bucket"
}

output "s3_bucket_arn" {
  value       = module.s3.raw_articles_bucket_arn
  description = "ARN of the S3 bucket"
}

output "s3_bucket_id" {
  value       = module.s3.raw_articles_bucket_id
  description = "ID of the S3 bucket"
}

output "neptune_cluster_endpoint" {
  value       = aws_neptune_cluster.knowledge_graphs.endpoint
  description = "Endpoint of the Neptune cluster"
}

output "neptune_cluster_port" {
  value       = aws_neptune_cluster.knowledge_graphs.port
  description = "Port of the Neptune cluster"
}

output "neptune_cluster_id" {
  value       = aws_neptune_cluster.knowledge_graphs.id
  description = "ID of the Neptune cluster"
}

output "neptune_iam_role_arn" {
  value       = aws_iam_role.neptune_s3_access.arn
  description = "ARN of the Neptune IAM role"
}

output "lambda_code_bucket_name" {
  value       = aws_s3_bucket.lambda_code.bucket
  description = "Name of the S3 bucket for Lambda code"
}

output "lambda_code_bucket_arn" {
  value       = aws_s3_bucket.lambda_code.arn
  description = "ARN of the S3 bucket for Lambda code"
}

output "neptune_load_bucket_name" {
  value       = aws_s3_bucket.neptune_load.bucket
  description = "Name of the S3 bucket for Neptune load data"
}

output "neptune_load_bucket_arn" {
  value       = aws_s3_bucket.neptune_load.arn
  description = "ARN of the S3 bucket for Neptune load data"
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
}
