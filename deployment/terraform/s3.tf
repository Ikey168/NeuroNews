# S3 bucket configuration for NeuroNews

# Bucket for storing raw scraped articles
resource "aws_s3_bucket" "raw_articles" {
  bucket = "${var.bucket_name_prefix}-raw-articles-${var.environment}"
  
  tags = merge(var.tags, {
    Name = "Raw Articles Storage"
    Description = "Stores raw scraped news articles before processing"
  })
}

# Enable versioning
resource "aws_s3_bucket_versioning" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Configure server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rules
resource "aws_s3_bucket_lifecycle_configuration" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  rule {
    id     = "archive_old_articles"
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
      days = 730  # Delete articles after 2 years
    }
  }
}

# CORS configuration
resource "aws_s3_bucket_cors_configuration" "raw_articles" {
  bucket = aws_s3_bucket.raw_articles.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = ["*"]  # You should restrict this in production
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}