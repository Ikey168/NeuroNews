# Variables for NeuroNews Terraform configuration

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_name_prefix" {
  description = "Prefix for the S3 bucket name"
  type        = string
  default     = "neuronews"
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "NeuroNews"
    ManagedBy   = "Terraform"
  }
}

# Redshift variables
variable "redshift_cluster_identifier" {
  description = "Identifier for the Redshift cluster"
  type        = string
  default     = "neuronews-redshift"
}

variable "redshift_database_name" {
  description = "Name of the database in the Redshift cluster"
  type        = string
  default     = "neuronews"
}

variable "redshift_master_username" {
  description = "Master username for the Redshift cluster"
  type        = string
  default     = "neuronews_admin"
}

variable "redshift_master_password" {
  description = "Master password for the Redshift cluster (should be provided via environment variables in production)"
  type        = string
  default     = "ChangeMe123!" # This is just a placeholder, should be overridden in production
  sensitive   = true
}

variable "redshift_node_type" {
  description = "Node type for the Redshift cluster"
  type        = string
  default     = "dc2.large" # Smallest node type for development
}

variable "redshift_cluster_type" {
  description = "Cluster type for the Redshift cluster (single-node or multi-node)"
  type        = string
  default     = "single-node" # Use single-node for development
}

variable "redshift_number_of_nodes" {
  description = "Number of nodes in the Redshift cluster (only applicable for multi-node clusters)"
  type        = number
  default     = 1
}

variable "redshift_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster"
  type        = bool
  default     = true # Set to false in production
}

# Neptune variables
variable "neptune_cluster_identifier" {
  description = "Identifier for the Neptune cluster"
  type        = string
  default     = "neuronews-neptune"
}

variable "neptune_instance_class" {
  description = "Instance class for the Neptune cluster"
  type        = string
  default     = "db.t3.medium" # Smallest instance class for development
}

variable "neptune_instance_count" {
  description = "Number of instances in the Neptune cluster"
  type        = number
  default     = 1 # Single instance for development
}

variable "neptune_master_username" {
  description = "Master username for the Neptune cluster"
  type        = string
  default     = "neptune_admin"
}

variable "neptune_master_password" {
  description = "Master password for the Neptune cluster (should be provided via environment variables in production)"
  type        = string
  default     = "ChangeMe456!" # This is just a placeholder, should be overridden in production
  sensitive   = true
}

variable "neptune_port" {
  description = "Port for the Neptune cluster"
  type        = number
  default     = 8182 # Default Neptune port
}

variable "neptune_preferred_backup_window" {
  description = "Preferred backup window for the Neptune cluster"
  type        = string
  default     = "02:00-03:00" # 2-3 AM UTC
}

variable "neptune_backup_retention_period" {
  description = "Backup retention period for the Neptune cluster in days"
  type        = number
  default     = 7 # 7 days for development
}

variable "neptune_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster"
  type        = bool
  default     = true # Set to false in production
}

variable "neptune_apply_immediately" {
  description = "Whether to apply changes immediately"
  type        = bool
  default     = true # Set to false in production
}

# Lambda variables
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
  type        = number
  default     = 300 # 5 minutes
}

variable "lambda_memory_size" {
  description = "Memory size for Lambda functions in MB"
  type        = number
  default     = 512
}

variable "lambda_concurrent_executions" {
  description = "Maximum concurrent executions for Lambda functions"
  type        = number
  default     = 10
}

variable "lambda_log_retention_days" {
  description = "Number of days to retain Lambda logs"
  type        = number
  default     = 14
}

variable "lambda_s3_key_prefix" {
  description = "Prefix for Lambda function code in S3"
  type        = string
  default     = "lambda-functions"
}
