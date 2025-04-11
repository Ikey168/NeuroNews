# Create an S3 bucket for Neptune bulk load data
resource "aws_s3_bucket" "neptune_load" {
  bucket = "${var.bucket_name_prefix}-neptune-load-${var.environment}"
  
  tags = merge(
    var.tags,
    {
      Name        = "NeuroNews Neptune Load Data"
      Environment = var.environment
    }
  )
}

# Enable versioning for the bucket
resource "aws_s3_bucket_versioning" "neptune_load_versioning" {
  bucket = aws_s3_bucket.neptune_load.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption for the bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "neptune_load_encryption" {
  bucket = aws_s3_bucket.neptune_load.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to the bucket
resource "aws_s3_bucket_public_access_block" "neptune_load_public_access_block" {
  bucket = aws_s3_bucket.neptune_load.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Create a bucket policy to allow Neptune to access the S3 bucket
resource "aws_s3_bucket_policy" "neptune_load_policy" {
  bucket = aws_s3_bucket.neptune_load.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.neptune_s3_access.arn
        }
        Resource = [
          aws_s3_bucket.neptune_load.arn,
          "${aws_s3_bucket.neptune_load.arn}/*"
        ]
      }
    ]
  })
}