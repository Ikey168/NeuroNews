# Network ACL for Neptune
resource "aws_network_acl" "neptune" {
  vpc_id = aws_vpc.main.id
  subnet_ids = aws_subnet.private[*].id

  ingress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = var.vpc_cidr
    from_port  = var.neptune_port
    to_port    = var.neptune_port
  }

  ingress {
    protocol   = "tcp"
    rule_no    = 200
    action     = "allow"
    cidr_block = var.vpc_cidr
    from_port  = 1024
    to_port    = 65535
  }

  egress {
    protocol   = "tcp"
    rule_no    = 100
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 443
    to_port    = 443
  }

  egress {
    protocol   = "tcp"
    rule_no    = 200
    action     = "allow"
    cidr_block = "0.0.0.0/0"
    from_port  = 1024
    to_port    = 65535
  }

  tags = merge(var.tags, {
    Name = "${var.environment}-neptune-nacl"
  })
}

# Neptune Security Group
resource "aws_security_group" "neptune" {
  name_prefix = "${var.environment}-neptune-"
  description = "Security group for Neptune cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port = var.neptune_port
    to_port   = var.neptune_port
    protocol  = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.environment}-neptune-sg"
  })
}

# Neptune Subnet Group
resource "aws_neptune_subnet_group" "main" {
  name        = "${var.environment}-neptune-subnet-group"
  description = "Neptune subnet group"
  subnet_ids  = aws_subnet.private[*].id

  tags = var.tags
}

# Neptune Parameter Group
resource "aws_neptune_parameter_group" "main" {
  family      = "neptune1.2"
  name        = "${var.environment}-neptune-param-group"
  description = "Neptune parameter group"

  parameter {
    name  = "neptune_enable_audit_logs"
    value = var.neptune_enable_audit_logs ? "1" : "0"
  }

  tags = var.tags
}

# Neptune Cluster
resource "aws_neptune_cluster" "main" {
  cluster_identifier                  = var.neptune_cluster_identifier
  engine                             = "neptune"
  engine_version                     = "1.2.1.0"
  neptune_cluster_parameter_group_name = aws_neptune_parameter_group.main.name
  vpc_security_group_ids            = [aws_security_group.neptune.id]
  neptune_subnet_group_name         = aws_neptune_subnet_group.main.name
  port                              = var.neptune_port
  backup_retention_period           = var.neptune_backup_retention_period
  preferred_backup_window           = var.neptune_preferred_backup_window
  skip_final_snapshot              = var.neptune_skip_final_snapshot
  iam_database_authentication_enabled = true

  tags = var.tags
}

# Neptune Instances
resource "aws_neptune_cluster_instance" "main" {
  count               = var.neptune_cluster_size
  cluster_identifier  = aws_neptune_cluster.main.id
  instance_class      = var.neptune_instance_class
  engine             = "neptune"
  neptune_parameter_group_name = aws_neptune_parameter_group.main.name

  tags = var.tags

  depends_on = [aws_neptune_cluster.main]
}

# IAM Role for Neptune
resource "aws_iam_role" "neptune" {
  name = "${var.environment}-neptune-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "neptune-db.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Neptune IAM Policy
resource "aws_iam_role_policy" "neptune" {
  name = "${var.environment}-neptune-policy"
  role = aws_iam_role.neptune.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.s3.bucket_arn,
          "${module.s3.bucket_arn}/*"
        ]
      }
    ]
  })
}

# VPC Endpoint for Neptune
resource "aws_vpc_endpoint" "neptune" {
  vpc_id             = aws_vpc.main.vpc_id
  service_name       = "com.amazonaws.${var.aws_region}.neptune-db"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.neptune.id]

  tags = merge(var.tags, {
    Name = "${var.environment}-neptune-vpce"
  })
}

# Outputs
output "neptune_cluster_endpoint" {
  description = "Neptune cluster endpoint"
  value       = aws_neptune_cluster.main.endpoint
}

output "neptune_cluster_port" {
  description = "Neptune cluster port"
  value       = aws_neptune_cluster.main.port
}

output "neptune_cluster_arn" {
  description = "Neptune cluster ARN"
  value       = aws_neptune_cluster.main.arn
}
