resource "aws_s3_bucket" "raw_articles" {
  bucket = "${var.bucket_name_prefix}-raw-articles-${var.environment}"

  tags = merge(
    var.tags,
    {
      Name        = "NeuroNews Raw Articles"
      Environment = var.environment
    }
  )
}

# Enable versioning for the bucket
resource "aws_s3_bucket_versioning" "raw_articles_versioning" {
  bucket = aws_s3_bucket.raw_articles.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption for the bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "raw_articles_encryption" {
  bucket = aws_s3_bucket.raw_articles.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to the bucket
resource "aws_s3_bucket_public_access_block" "raw_articles_public_access_block" {
  bucket = aws_s3_bucket.raw_articles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Configure lifecycle rules for the bucket
resource "aws_s3_bucket_lifecycle_configuration" "raw_articles_lifecycle" {
  bucket = aws_s3_bucket.raw_articles.id

  rule {
    id     = "archive-old-articles"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }

    expiration {
      days = 1095
    }

    filter {
      prefix = ""
    }
  }

  lifecycle {
    ignore_changes = [rule]
  }
}