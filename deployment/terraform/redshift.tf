# AWS Redshift Cluster for NeuroNews processed texts

# Create a security group for Redshift
resource "aws_security_group" "redshift" {
  name        = "${var.redshift_cluster_identifier}-${var.environment}-sg"
  description = "Security group for Redshift cluster"
  
  # Allow inbound traffic on the Redshift port (5439)
  ingress {
    from_port   = 5439
    to_port     = 5439
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
      Name        = "${var.redshift_cluster_identifier}-${var.environment}-sg"
      Environment = var.environment
    }
  )
}

# Create a parameter group for Redshift
resource "aws_redshift_parameter_group" "redshift" {
  name        = "${var.redshift_cluster_identifier}-${var.environment}-params"
  description = "Parameter group for ${var.redshift_cluster_identifier} Redshift cluster"
  family      = "redshift-1.0"
  
  parameter {
    name  = "enable_user_activity_logging"
    value = "true"
  }
  
  parameter {
    name  = "require_ssl"
    value = "true"
  }
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.redshift_cluster_identifier}-${var.environment}-params"
      Environment = var.environment
    }
  )
}

# Create a subnet group for Redshift
# Note: This requires existing VPC and subnets, which would typically be defined in a separate network.tf file
# For simplicity, we're using the default VPC and subnets here
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_redshift_subnet_group" "redshift" {
  name        = "${var.redshift_cluster_identifier}-${var.environment}-subnet-group"
  description = "Subnet group for ${var.redshift_cluster_identifier} Redshift cluster"
  subnet_ids  = data.aws_subnets.default.ids
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.redshift_cluster_identifier}-${var.environment}-subnet-group"
      Environment = var.environment
    }
  )
}

# Create the Redshift cluster
resource "aws_redshift_cluster" "processed_texts" {
  cluster_identifier        = "${var.redshift_cluster_identifier}-${var.environment}"
  database_name             = var.redshift_database_name
  master_username           = var.redshift_master_username
  master_password           = var.redshift_master_password
  node_type                 = var.redshift_node_type
  cluster_type              = var.redshift_cluster_type
  number_of_nodes           = var.redshift_cluster_type == "multi-node" ? var.redshift_number_of_nodes : null
  
  # Security
  encrypted                 = true
  enhanced_vpc_routing      = true
  publicly_accessible       = false
  vpc_security_group_ids    = [aws_security_group.redshift.id]
  
  # Configuration
  cluster_parameter_group_name = aws_redshift_parameter_group.redshift.name
  cluster_subnet_group_name    = aws_redshift_subnet_group.redshift.name
  iam_roles                    = []
  
  # Maintenance
  automated_snapshot_retention_period = 7
  skip_final_snapshot                 = var.redshift_skip_final_snapshot
  final_snapshot_identifier           = var.redshift_skip_final_snapshot ? null : "${var.redshift_cluster_identifier}-${var.environment}-final-snapshot"
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.redshift_cluster_identifier}-${var.environment}",
      Environment = var.environment
    }
  )
  
  # Set prevent_destroy to false to allow testing
  lifecycle {
    prevent_destroy = false
  }
}
