# Variables for NeuroNews Terraform configuration

# ===== General Configuration =====

variable "aws_region" {
  description = "AWS region to deploy resources (e.g., us-east-1, eu-west-1)"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^(us|eu|ap|sa|ca|me|af)-(north|south|east|west|central)-[1-3]$", var.aws_region))
    error_message = "The aws_region must be a valid AWS region format (e.g., us-east-1, eu-west-1)."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "The environment must be one of: dev, staging, prod."
  }
}

variable "bucket_name_prefix" {
  description = "Prefix for the S3 bucket name (will be combined with environment)"
  type        = string
  default     = "neuronews"
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project   = "NeuroNews"
    ManagedBy = "Terraform"
  }
}

# ===== Redshift Configuration =====

variable "redshift_cluster_identifier" {
  description = "Identifier for the Redshift cluster (will be combined with environment)"
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
  default     = "ikeyaws"
}

variable "redshift_master_password" {
  description = "Master password for the Redshift cluster. DO NOT set a default value here. Should be provided via AWS Secrets Manager or environment variable TF_VAR_redshift_master_password."
  type        = string
  sensitive   = true
  # No default value - must be provided externally
}

variable "redshift_node_type" {
  description = "Node type for the Redshift cluster (e.g., dc2.large, ra3.xlplus)"
  type        = string
  default     = "dc2.large" # Smallest node type for development

  validation {
    condition     = can(regex("^(dc2|ra3)\\.(large|xlplus|4xlarge|16xlarge)$", var.redshift_node_type))
    error_message = "The redshift_node_type must be a valid Redshift node type (e.g., dc2.large, ra3.xlplus)."
  }
}

variable "redshift_cluster_type" {
  description = "Cluster type for the Redshift cluster (single-node or multi-node)"
  type        = string
  default     = "single-node" # Use single-node for development

  validation {
    condition     = contains(["single-node", "multi-node"], var.redshift_cluster_type)
    error_message = "The redshift_cluster_type must be either 'single-node' or 'multi-node'."
  }
}

variable "redshift_number_of_nodes" {
  description = "Number of nodes in the Redshift cluster (only applicable for multi-node clusters)"
  type        = number
  default     = 1

  validation {
    condition     = var.redshift_number_of_nodes >= 1 && var.redshift_number_of_nodes <= 128
    error_message = "The redshift_number_of_nodes must be between 1 and 128."
  }
}

variable "redshift_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster (true for dev/staging, false for production)"
  type        = bool
  default     = true # Set to false in production
}

# ===== Neptune Configuration =====

variable "neptune_cluster_identifier" {
  description = "Identifier for the Neptune cluster (will be combined with environment)"
  type        = string
  default     = "neuronews-neptune"
}

variable "neptune_instance_class" {
  description = "Instance class for the Neptune cluster (e.g., db.t3.medium, db.r5.large)"
  type        = string
  default     = "db.t3.medium" # Smallest instance class for development

  validation {
    condition     = can(regex("^db\\.(t3|r5|r6g)\\.(medium|large|xlarge|2xlarge|4xlarge|8xlarge|12xlarge)$", var.neptune_instance_class))
    error_message = "The neptune_instance_class must be a valid Neptune instance class (e.g., db.t3.medium, db.r5.large)."
  }
}

variable "neptune_instance_count" {
  description = "Number of instances in the Neptune cluster (1 for dev/staging, 2+ for production)"
  type        = number
  default     = 1 # Single instance for development

  validation {
    condition     = var.neptune_instance_count >= 1 && var.neptune_instance_count <= 16
    error_message = "The neptune_instance_count must be between 1 and 16."
  }
}

variable "neptune_port" {
  description = "Port for the Neptune cluster"
  type        = number
  default     = 8182 # Default Neptune port

  validation {
    condition     = var.neptune_port > 1024 && var.neptune_port < 65535
    error_message = "The neptune_port must be between 1025 and 65534."
  }
}

variable "neptune_preferred_backup_window" {
  description = "Preferred backup window for the Neptune cluster (format: hh24:mi-hh24:mi)"
  type        = string
  default     = "02:00-03:00" # 2-3 AM UTC

  validation {
    condition     = can(regex("^([0-1][0-9]|2[0-3]):([0-5][0-9])-([0-1][0-9]|2[0-3]):([0-5][0-9])$", var.neptune_preferred_backup_window))
    error_message = "The neptune_preferred_backup_window must be in the format hh24:mi-hh24:mi."
  }
}

variable "neptune_backup_retention_period" {
  description = "Backup retention period for the Neptune cluster in days (1-35)"
  type        = number
  default     = 7 # 7 days for development

  validation {
    condition     = var.neptune_backup_retention_period >= 1 && var.neptune_backup_retention_period <= 35
    error_message = "The neptune_backup_retention_period must be between 1 and 35 days."
  }
}

variable "neptune_skip_final_snapshot" {
  description = "Whether to skip the final snapshot when destroying the cluster (true for dev/staging, false for production)"
  type        = bool
  default     = true # Set to false in production
}

variable "neptune_apply_immediately" {
  description = "Whether to apply changes immediately (true for dev/staging, false for production)"
  type        = bool
  default     = true # Set to false in production
}

# ===== Lambda Configuration =====

variable "lambda_function_prefix" {
  description = "Prefix for Lambda function names (will be combined with environment)"
  type        = string
  default     = "neuronews"
}

variable "lambda_runtime" {
  description = "Runtime for Lambda functions (e.g., python3.9, nodejs16.x)"
  type        = string
  default     = "python3.9"

  validation {
    condition     = can(regex("^(python3\\.[0-9]|nodejs[0-9]{1,2}\\.x|java[0-9]{1,2}|dotnetcore[0-9]\\.[0-9]|go[0-9]\\.[0-9]|ruby[0-9]\\.[0-9]|provided)$", var.lambda_runtime))
    error_message = "The lambda_runtime must be a valid Lambda runtime (e.g., python3.9, nodejs16.x)."
  }
}

variable "lambda_timeout" {
  description = "Timeout for Lambda functions in seconds (1-900)"
  type        = number
  default     = 300 # 5 minutes

  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "The lambda_timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_memory_size" {
  description = "Memory size for Lambda functions in MB (128-10240, in 64MB increments)"
  type        = number
  default     = 512

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240 && var.lambda_memory_size % 64 == 0
    error_message = "The lambda_memory_size must be between 128 and 10240 MB, in 64MB increments."
  }
}

variable "lambda_concurrent_executions" {
  description = "Maximum concurrent executions for Lambda functions (0-1000, 0 for unlimited)"
  type        = number
  default     = 10

  validation {
    condition     = var.lambda_concurrent_executions >= 0 && var.lambda_concurrent_executions <= 1000
    error_message = "The lambda_concurrent_executions must be between 0 and 1000."
  }
}

variable "lambda_log_retention_days" {
  description = "Number of days to retain Lambda logs (1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653)"
  type        = number
  default     = 14

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.lambda_log_retention_days)
    error_message = "The lambda_log_retention_days must be one of: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653."
  }
}

variable "lambda_s3_key_prefix" {
  description = "Prefix for Lambda function code in S3"
  type        = string
  default     = "lambda-functions"
}

# ===== IAM Configuration =====

variable "trusted_account_id" {
  description = "AWS account ID that is trusted for cross-account access"
  type        = string
  default     = "" # Empty string disables cross-account access

  validation {
    condition     = var.trusted_account_id == "" || can(regex("^[0-9]{12}$", var.trusted_account_id))
    error_message = "The trusted_account_id must be empty or a 12-digit AWS account ID."
  }
}

variable "create_admin_group" {
  description = "Whether to create an administrators group"
  type        = bool
  default     = true
}

variable "create_developer_group" {
  description = "Whether to create a developers group"
  type        = bool
  default     = true
}

variable "create_cicd_user" {
  description = "Whether to create a CI/CD user"
  type        = bool
  default     = true
}

variable "create_cross_account_role" {
  description = "Whether to create a cross-account role (disabled by default for security)"
  type        = bool
  default     = false
}
