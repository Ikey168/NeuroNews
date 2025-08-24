# Data source for account information
data "aws_caller_identity" "current" {}

# Scraper Service Role
resource "aws_iam_role" "scraper_role" {
  name = "neuronews-scraper-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = ["ec2.amazonaws.com", "lambda.amazonaws.com"]
        }
        Condition = {
          StringEquals = {
            "aws:RequestedRegion": var.aws_region
          }
          IpAddress = {
            "aws:SourceIp": var.allowed_ips
          }
        }
      }
    ]
  })

  tags = {
    Environment = var.environment
    Service     = "scraper"
  }
}

# Scraper Service Policy
resource "aws_iam_role_policy" "scraper_policy" {
  name = "neuronews-scraper-policy"
  role = aws_iam_role.scraper_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${module.s3.raw_articles_bucket_arn}",
          "${module.s3.raw_articles_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/scraper-*"]
      }
    ]
  })
}

# API Service Role
resource "aws_iam_role" "api_role" {
  name = "neuronews-api-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = ["ecs-tasks.amazonaws.com", "apigateway.amazonaws.com"]
        }
        Condition = {
          StringEquals = {
            "aws:RequestedRegion": var.aws_region
          }
          IpAddress = {
            "aws:SourceIp": var.allowed_ips
          }
        }
      }
    ]
  })

  tags = {
    Environment = var.environment
    Service     = "api"
  }
}

# API Service Policy
resource "aws_iam_role_policy" "api_policy" {
  name = "neuronews-api-policy"
  role = aws_iam_role.api_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:ReadDataViaQuery",
          "neptune-db:GetQueryStatus",
          "neptune-db:CancelQuery"
        ]
        Resource = ["${aws_neptune_cluster.main.arn}"]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/*"]
      }
    ]
  })
}

# CloudTrail Configuration
resource "aws_cloudtrail" "neuronews_trail" {
  name                          = "neuronews-audit-trail-${var.environment}"
  s3_bucket_name               = aws_s3_bucket.audit_logs.id
  include_global_service_events = true
  is_multi_region_trail        = false
  enable_log_file_validation   = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type   = "AWS::S3::Object"
      values = ["${module.s3.raw_articles_bucket_arn}/"]
    }
  }

  tags = {
    Environment = var.environment
    Service     = "audit"
  }
}

# Audit Logs Bucket
resource "aws_s3_bucket" "audit_logs" {
  bucket = "neuronews-audit-logs-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Environment = var.environment
    Service     = "audit"
  }
}

# S3 Bucket Versioning
resource "aws_s3_bucket_versioning" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket Server Side Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 Bucket Lifecycle Configuration
resource "aws_s3_bucket_lifecycle_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    id     = "audit_logs_retention"
    status = "Enabled"

    expiration {
      days = 365
    }
  }
}

# CloudTrail Bucket Policy
resource "aws_s3_bucket_policy" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.audit_logs.arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.audit_logs.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}
