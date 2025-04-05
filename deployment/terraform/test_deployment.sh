#!/bin/bash
# Test script for NeuroNews Terraform infrastructure deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting NeuroNews infrastructure deployment test...${NC}"

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}Error: Terraform is not installed. Please install Terraform first.${NC}"
    echo "Visit https://learn.hashicorp.com/tutorials/terraform/install-cli for installation instructions."
    exit 1
fi

# Check Terraform version
TERRAFORM_VERSION=$(terraform version -json | jq -r '.terraform_version')
echo -e "${GREEN}Terraform version: ${TERRAFORM_VERSION}${NC}"

# Initialize Terraform
echo -e "${YELLOW}Initializing Terraform...${NC}"
terraform init

# Validate Terraform configuration
echo -e "${YELLOW}Validating Terraform configuration...${NC}"
terraform validate

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Terraform configuration is valid.${NC}"
else
    echo -e "${RED}Terraform configuration is invalid.${NC}"
    exit 1
fi

# Create a plan
echo -e "${YELLOW}Creating Terraform plan...${NC}"
terraform plan -var="environment=test" -out=test.tfplan

# Show the plan
echo -e "${YELLOW}Showing Terraform plan...${NC}"
terraform show test.tfplan

echo -e "${GREEN}Test completed successfully!${NC}"
echo "To apply the plan, run: terraform apply test.tfplan"
echo "To destroy the infrastructure after testing, run: terraform destroy -var=\"environment=test\""
