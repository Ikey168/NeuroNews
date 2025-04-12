variable "bucket_name_prefix" {
  type        = string
  description = "Prefix for all bucket names"
  default     = "neuronews"
}

variable "environment" {
  type        = string
  description = "Environment (dev, prod, etc.)"
}

variable "lambda_function_prefix" {
  type        = string
  description = "Prefix for all Lambda function names"
  default     = "neuronews"
}

variable "redshift_cluster_identifier" {
  type        = string
  description = "Identifier for the Redshift cluster"
  default     = "neuronews-redshift"
}

variable "redshift_master_password" {
  type        = string
  description = "Master password for the Redshift cluster. DO NOT set a default value here. Should be provided via AWS Secrets Manager or environment variable TF_VAR_redshift_master_password."
  sensitive   = true
}

variable "trusted_account_id" {
  type        = string
  description = "AWS account ID to trust for cross-account access (optional)"
  default     = ""
}

variable "create_cross_account_role" {
  type        = bool
  description = "Whether to create a cross-account role"
  default     = false
}

variable "create_admin_group" {
  type        = bool
  description = "Whether to create an administrator IAM group"
  default     = true
}

variable "create_developer_group" {
  type        = bool
  description = "Whether to create a developer IAM group"
  default     = true
}

variable "create_cicd_user" {
  type        = bool
  description = "Whether to create a CI/CD IAM user"
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to all resources"
  default = {
    Project   = "NeuroNews"
    ManagedBy = "Terraform"
  }
}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy to"
  default     = "us-east-1"
}

variable "lambda_s3_key_prefix" {
  type        = string
  description = "Prefix for Lambda function S3 keys"
  default     = "lambda-functions"
}

variable "lambda_runtime" {
  type        = string
  description = "Lambda runtime"
  default     = "python3.9"
}

variable "lambda_timeout" {
  type        = number
  description = "Lambda timeout"
  default     = 300
}

variable "lambda_memory_size" {
  type        = number
  description = "Lambda memory size"
  default     = 128
}

variable "lambda_concurrent_executions" {
  type        = number
  description = "Lambda reserved concurrent executions"
  default     = 10
}

variable "lambda_log_retention_days" {
  type        = number
  description = "Lambda log retention days"
  default     = 7
}

variable "redshift_database_name" {
  type        = string
  description = "Name of the Redshift database"
  default     = "neuronews"
}

variable "redshift_master_username" {
  type        = string
  description = "Master username for the Redshift cluster"
  default     = "awsuser"
}

variable "redshift_node_type" {
  type        = string
  description = "Node type for the Redshift cluster"
  default     = "dc2.large"
}

variable "redshift_cluster_type" {
  type        = string
  description = "Cluster type for the Redshift cluster"
  default     = "single-node"
}

variable "redshift_number_of_nodes" {
  type        = number
  description = "Number of nodes for the Redshift cluster (only applicable for multi-node clusters)"
  default     = 2
}

variable "redshift_skip_final_snapshot" {
  type        = bool
  description = "Whether to skip the final snapshot for the Redshift cluster"
  default     = true
}

variable "neptune_cluster_identifier" {
  type        = string
  description = "Identifier for the Neptune cluster"
  default     = "neuronews-neptune"
}

variable "neptune_port" {
  type        = number
  description = "Port for the Neptune cluster"
  default     = 8182
}

variable "neptune_backup_retention_period" {
  type        = number
  description = "Backup retention period for the Neptune cluster"
  default     = 7
}

variable "neptune_preferred_backup_window" {
  type        = string
  description = "Preferred backup window for the Neptune cluster"
  default     = "07:00-09:00"
}

variable "neptune_skip_final_snapshot" {
  type        = bool
  description = "Whether to skip the final snapshot for the Neptune cluster"
  default     = true
}

variable "neptune_apply_immediately" {
  type        = bool
  description = "Whether to apply changes immediately for the Neptune cluster"
  default     = true
}

variable "neptune_master_username" {
  type        = string
  description = "Master username for the Neptune cluster"
  default     = "admin"
}

variable "neptune_master_password" {
  type        = string
  description = "Master password for the Neptune cluster"
  sensitive   = true
}

variable "neptune_instance_count" {
  type        = number
  description = "Number of Neptune cluster instances"
  default     = 1
}

variable "neptune_instance_class" {
  type        = string
  description = "Instance class for the Neptune cluster instances"
  default     = "db.r5.large"
}
