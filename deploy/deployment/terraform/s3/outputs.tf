output "raw_articles_bucket_name" {
  description = "The name of the raw articles S3 bucket"
  value       = aws_s3_bucket.raw_articles.bucket
}

output "raw_articles_bucket_arn" {
  description = "The ARN of the raw articles S3 bucket"
  value       = aws_s3_bucket.raw_articles.arn
}

output "raw_articles_bucket_id" {
  description = "The ID of the raw articles S3 bucket"
  value       = aws_s3_bucket.raw_articles.id
}

output "lambda_code_bucket_name" {
  description = "The name of the Lambda code S3 bucket"
  value       = aws_s3_bucket.lambda_code.bucket
}

output "lambda_code_bucket_arn" {
  description = "The ARN of the Lambda code S3 bucket"
  value       = aws_s3_bucket.lambda_code.arn
}

output "lambda_code_bucket_id" {
  description = "The ID of the Lambda code S3 bucket"
  value       = aws_s3_bucket.lambda_code.id
}