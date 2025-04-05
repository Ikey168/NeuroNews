# AWS Neptune Cluster for NeuroNews Knowledge Graphs

# Create a security group for Neptune
resource "aws_security_group" "neptune" {
  name        = "${var.neptune_cluster_identifier}-${var.environment}-sg"
  description = "Security group for Neptune cluster"
  
  # Allow inbound traffic on the Neptune port (8182)
  ingress {
    from_port   = var.neptune_port
    to_port     = var.neptune_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # In production, restrict this to specific IPs
  }
  
  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}-sg"
      Environment = var.environment
    }
  )
}

# Create an IAM role for Neptune to access S3
resource "aws_iam_role" "neptune_s3_access" {
  name = "${var.neptune_cluster_identifier}-${var.environment}-s3-access"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}-s3-access"
      Environment = var.environment
    }
  )
}

# Attach the AmazonS3ReadOnlyAccess policy to the IAM role
resource "aws_iam_role_policy_attachment" "neptune_s3_access" {
  role       = aws_iam_role.neptune_s3_access.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create a parameter group for Neptune
resource "aws_neptune_parameter_group" "neptune" {
  name        = "${var.neptune_cluster_identifier}-${var.environment}-params"
  family      = "neptune1"
  description = "Parameter group for ${var.neptune_cluster_identifier} Neptune cluster"
  
  # Neptune doesn't have many modifiable parameters at the parameter group level
  # Most configurations are done at the cluster level
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}-params"
      Environment = var.environment
    }
  )
}

# Create a subnet group for Neptune
# Note: This requires existing VPC and subnets, which would typically be defined in a separate network.tf file
# For simplicity, we're using the default VPC and subnets here
resource "aws_neptune_subnet_group" "neptune" {
  name        = "${var.neptune_cluster_identifier}-${var.environment}-subnet-group"
  description = "Subnet group for ${var.neptune_cluster_identifier} Neptune cluster"
  subnet_ids  = data.aws_subnets.default.ids
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}-subnet-group"
      Environment = var.environment
    }
  )
}

# Create the Neptune cluster
resource "aws_neptune_cluster" "knowledge_graphs" {
  cluster_identifier                  = "${var.neptune_cluster_identifier}-${var.environment}"
  engine                              = "neptune"
  engine_version                      = "1.2.0.0" # Use the latest version available
  backup_retention_period             = var.neptune_backup_retention_period
  preferred_backup_window             = var.neptune_preferred_backup_window
  skip_final_snapshot                 = var.neptune_skip_final_snapshot
  final_snapshot_identifier           = var.neptune_skip_final_snapshot ? null : "${var.neptune_cluster_identifier}-${var.environment}-final-snapshot"
  apply_immediately                   = var.neptune_apply_immediately
  vpc_security_group_ids              = [aws_security_group.neptune.id]
  neptune_subnet_group_name           = aws_neptune_subnet_group.neptune.name
  iam_database_authentication_enabled = true
  
  # Optional: Set master credentials
  # Neptune can operate without credentials using IAM authentication
  # But we'll set them for compatibility with tools that require basic auth
  master_username = var.neptune_master_username
  master_password = var.neptune_master_password
  
  # Enable storage encryption
  storage_encrypted = true
  
  # Enable CloudWatch logs export
  enable_cloudwatch_logs_exports = ["audit"]
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}"
      Environment = var.environment
    }
  )
  
  # Prevent destruction in production
  lifecycle {
    prevent_destroy = var.environment == "prod" ? true : false
  }
}

# Create Neptune cluster instances
resource "aws_neptune_cluster_instance" "knowledge_graphs" {
  count                        = var.neptune_instance_count
  identifier                   = "${var.neptune_cluster_identifier}-${var.environment}-${count.index}"
  cluster_identifier           = aws_neptune_cluster.knowledge_graphs.id
  instance_class               = var.neptune_instance_class
  engine                       = "neptune"
  apply_immediately            = var.neptune_apply_immediately
  neptune_parameter_group_name = aws_neptune_parameter_group.neptune.name
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.neptune_cluster_identifier}-${var.environment}-${count.index}"
      Environment = var.environment
    }
  )
  
  # Prevent destruction in production
  lifecycle {
    prevent_destroy = var.environment == "prod" ? true : false
  }
}

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
