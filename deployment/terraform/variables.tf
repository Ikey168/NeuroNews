<<<<<<< HEAD
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
=======
variable "bucket_name_prefix" {
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
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
<<<<<<< HEAD
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {
    Project     = "NeuroNews"
    Environment = "dev"
    Terraform   = "true"
  }
}

variable "lambda_function_prefix" {
  description = "Prefix for Lambda function names"
  type        = string
  default     = "neuronews"
}

variable "lambda_runtime" {
  description = "Runtime for Lambda functions"
  type        = string
=======
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
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
  default     = "python3.9"
}

variable "lambda_timeout" {
<<<<<<< HEAD
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
=======
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
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
  type        = string
  description = "Name of the Redshift database"
  default     = "neuronews"
}

variable "redshift_master_username" {
  type        = string
  description = "Master username for the Redshift cluster"
<<<<<<< HEAD
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
=======
  default     = "awsuser"
}

variable "redshift_node_type" {
  type        = string
  description = "Node type for the Redshift cluster"
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
  default     = "dc2.large"
}

variable "redshift_cluster_type" {
<<<<<<< HEAD
  description = "Type of cluster (single-node or multi-node)"
  type        = string
=======
  type        = string
  description = "Cluster type for the Redshift cluster"
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
  default     = "single-node"
}

variable "redshift_number_of_nodes" {
<<<<<<< HEAD
  description = "Number of nodes in the Redshift cluster (if multi-node)"
  type        = number
  default     = 1
}

variable "redshift_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster"
  type        = bool
  default     = true
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
=======
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
>>>>>>> 7ddfa7248b922990347983877c08974738dd4bf4
}
