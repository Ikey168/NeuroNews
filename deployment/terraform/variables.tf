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
