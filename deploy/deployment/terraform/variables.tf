# General Configuration
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
}

variable "allowed_ips" {
  description = "List of allowed IP CIDR ranges for accessing services"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # Default to all IPs, should be restricted in production
}

# S3 Configuration
variable "bucket_name_prefix" {
  description = "Prefix for S3 bucket names"
  type        = string
  default     = "neuronews"
}

# Neptune Configuration
variable "neptune_cluster_identifier" {
  description = "Identifier for Neptune cluster"
  type        = string
  default     = "knowledge-graph"
}

variable "neptune_instance_class" {
  description = "Instance class for Neptune nodes"
  type        = string
  default     = "db.r5.large"
}

variable "neptune_port" {
  description = "Port for Neptune cluster"
  type        = number
  default     = 8182
}

variable "neptune_enable_audit_logs" {
  description = "Enable audit logging for Neptune"
  type        = bool
  default     = true
}

variable "neptune_cluster_size" {
  description = "Number of instances in Neptune cluster"
  type        = number
  default     = 1
}

variable "neptune_backup_retention_period" {
  description = "Number of days to retain Neptune backups"
  type        = number
  default     = 7
}

variable "neptune_preferred_backup_window" {
  description = "Preferred backup window for Neptune"
  type        = string
  default     = "03:00-04:00"
}

variable "neptune_skip_final_snapshot" {
  description = "Skip final snapshot when destroying Neptune cluster"
  type        = bool
  default     = false
}

# Lambda Configuration
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
  default     = 300
}

variable "lambda_memory_size" {
  description = "Memory allocation for Lambda functions in MB"
  type        = number
  default     = 512
}

variable "lambda_log_retention_days" {
  description = "Number of days to retain Lambda logs"
  type        = number
  default     = 30
}

# Cross-Account Access
variable "create_cross_account_role" {
  description = "Create IAM role for cross-account access"
  type        = bool
  default     = false
}

variable "trusted_account_id" {
  description = "AWS account ID to trust for cross-account access"
  type        = string
  default     = ""
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

# Tags
variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project = "NeuroNews"
    Owner   = "DataTeam"
  }
}

# Security Monitoring
variable "cloudtrail_retention_days" {
  description = "Number of days to retain CloudTrail logs"
  type        = number
  default     = 365
}

# News Scraper Lambda Configuration
variable "lambda_scraper_timeout" {
  description = "Timeout for news scraper Lambda function in seconds"
  type        = number
  default     = 900  # 15 minutes - optimized for scraping operations
}

variable "lambda_scraper_memory_size" {
  description = "Memory allocation for news scraper Lambda function in MB"
  type        = number
  default     = 1024  # 1GB - optimized for web scraping workloads
}

variable "scraper_schedule_expression" {
  description = "EventBridge schedule expression for automated scraping"
  type        = string
  default     = "rate(2 hours)"  # Run every 2 hours by default
}

variable "scraper_sources" {
  description = "List of news sources to scrape"
  type        = list(string)
  default     = ["bbc", "cnn", "reuters", "techcrunch"]
}

variable "scraper_max_articles_per_source" {
  description = "Maximum number of articles to scrape per source"
  type        = number
  default     = 15
}

variable "scraper_concurrent_requests" {
  description = "Number of concurrent requests for scraping"
  type        = number
  default     = 8  # Optimized for Lambda environment
}

variable "scraper_timeout" {
  description = "Timeout for individual scraper requests in seconds"
  type        = number
  default     = 30
}
