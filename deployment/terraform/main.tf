# Configure AWS provider
provider "aws" {
  region = var.aws_region
}

# Create an S3 bucket module
module "s3" {
  source = "./s3"
  
  bucket_name_prefix = var.bucket_name_prefix
  environment       = var.environment
  tags             = var.tags
}

# All S3-related resources are defined in s3.tf
# All IAM-related resources are defined in iam.tf
# All outputs are defined in outputs.tf
