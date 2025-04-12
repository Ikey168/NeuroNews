# S3 bucket for Lambda code
resource "aws_s3_bucket" "lambda_code" {
  bucket = "${var.bucket_name_prefix}-lambda-code-${var.environment}"

  tags = merge(
    var.tags,
    {
      Name        = "NeuroNews Lambda Code",
      Environment = var.environment
    }
  )
}