# Configure AWS provider
provider "aws" {
  region = var.aws_region
}

# All S3-related resources are defined in s3.tf
# All IAM-related resources are defined in iam.tf
# All outputs are defined in outputs.tf
