# General Variables
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_name_prefix" {
  description = "Prefix for S3 bucket names"
  type        = string
  default     = "neuronews"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {
    Project     = "NeuroNews"
    Environment = "dev"
    Terraform   = "true"
  }
}

# Lambda Function Variables
variable "lambda_function_prefix" {
  description = "Prefix for Lambda function names"
  type        = string
  default     = "neuronews"
}

variable "lambda_runtime" {
  description = "Runtime for Lambda functions"
  type        = string
  default     = "python3.9"
}

variable "lambda_timeout" {
  description = "Timeout for Lambda functions in seconds"
  type        = string
  default     = "300"
}

variable "lambda_memory_size" {
  description = "Memory size for Lambda functions in MB"
  type        = number
  default     = 256
}

variable "lambda_log_retention_days" {
  description = "Number of days to retain Lambda logs"
  type        = number
  default     = 14
}

# IAM Variables
variable "create_admin_group" {
  description = "Whether to create an admin IAM group"
  type        = bool
  default     = false
}

variable "create_developer_group" {
  description = "Whether to create a developer IAM group"
  type        = bool
  default     = false
}

variable "create_cicd_user" {
  description = "Whether to create a CI/CD IAM user"
  type        = bool
  default     = false
}

variable "create_cross_account_role" {
  description = "Whether to create a cross-account role"
  type        = bool
  default     = false
}

variable "trusted_account_id" {
  description = "AWS account ID that can assume the cross-account role"
  type        = string
  default     = ""
}

# Redshift Variables
variable "redshift_cluster_identifier" {
  description = "Identifier for the Redshift cluster"
  type        = string
  default     = "neuronews"
}

variable "redshift_database_name" {
  description = "Name of the first database to be created in the Redshift cluster"
  type        = string
  default     = "neuronews"
}

variable "redshift_master_username" {
  description = "Master username for the Redshift cluster"
  type        = string
  default     = "admin"
}

variable "redshift_master_password" {
  description = "Master password for the Redshift cluster"
  type        = string
  sensitive   = true
}

variable "redshift_node_type" {
  description = "Node type to be provisioned for the Redshift cluster"
  type        = string
  default     = "dc2.large"
}

variable "redshift_cluster_type" {
  description = "Type of cluster (single-node or multi-node)"
  type        = string
  default     = "single-node"
}

variable "redshift_number_of_nodes" {
  description = "Number of nodes in the Redshift cluster (if multi-node)"
  type        = number
  default     = 1
}

variable "redshift_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster"
  type        = bool
  default     = true
}

# Networking Variables
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# Neptune Variables
variable "neptune_cluster_identifier" {
  description = "Identifier for the Neptune cluster"
  type        = string
  default     = "neuronews"
}

variable "neptune_instance_class" {
  description = "Instance class for Neptune instances"
  type        = string
  default     = "db.t3.medium"
}

variable "neptune_cluster_size" {
  description = "Number of instances in the Neptune cluster"
  type        = number
  default     = 1
}

variable "neptune_port" {
  description = "Port on which Neptune accepts connections"
  type        = number
  default     = 8182
}

variable "neptune_enable_audit_logs" {
  description = "Enable audit logging for Neptune"
  type        = bool
  default     = false
}

variable "neptune_backup_retention_period" {
  description = "Number of days to retain Neptune backups"
  type        = number
  default     = 7
}

variable "neptune_preferred_backup_window" {
  description = "Preferred backup window for Neptune cluster (UTC)"
  type        = string
  default     = "03:00-04:00"
}

variable "neptune_skip_final_snapshot" {
  description = "Whether to skip final snapshot when destroying the cluster"
  type        = bool
  default     = true
}
