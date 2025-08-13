#!/bin/bash

# Lambda Deployment Script for NeuroNews Scraper
# This script packages and deploys the news scraper Lambda function

set -e  # Exit on any error

# Configuration
FUNCTION_NAME="news_scraper"
LAMBDA_DIR="deployment/terraform/lambda_functions"
SOURCE_DIR="src"
REQUIREMENTS_FILE="requirements.txt"
ZIP_FILE="${LAMBDA_DIR}/${FUNCTION_NAME}.zip"
AWS_REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 NeuroNews Lambda Deployment Script${NC}"
echo -e "${BLUE}======================================${NC}"
echo "Function: ${FUNCTION_NAME}"
echo "Environment: ${ENVIRONMENT}"
echo "AWS Region: ${AWS_REGION}"
echo ""

# Function to print status messages
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
print_status "Checking prerequisites..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if zip is installed
if ! command -v zip &> /dev/null; then
    print_error "zip command is not found. Please install zip utility."
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3."
    exit 1
fi

# Check if required directories exist
if [ ! -d "${SOURCE_DIR}" ]; then
    print_error "Source directory '${SOURCE_DIR}' not found."
    exit 1
fi

if [ ! -d "${LAMBDA_DIR}" ]; then
    print_warning "Lambda directory '${LAMBDA_DIR}' not found. Creating it..."
    mkdir -p "${LAMBDA_DIR}"
fi

print_status "Prerequisites check completed ✅"

# Clean up previous build
print_status "Cleaning up previous builds..."
rm -f "${ZIP_FILE}"
rm -rf "${LAMBDA_DIR}/package"
rm -rf "${LAMBDA_DIR}/temp"

# Create temporary directory for packaging
print_status "Creating temporary packaging directory..."
mkdir -p "${LAMBDA_DIR}/temp"
mkdir -p "${LAMBDA_DIR}/package"

# Copy source code
print_status "Copying source code..."
cp -r "${SOURCE_DIR}"/* "${LAMBDA_DIR}/temp/"

# Copy Lambda function
cp "${LAMBDA_DIR}/${FUNCTION_NAME}.py" "${LAMBDA_DIR}/temp/"

# Create requirements.txt for Lambda-specific dependencies
print_status "Creating Lambda requirements.txt..."
cat > "${LAMBDA_DIR}/temp/requirements_lambda.txt" << EOF
# Core dependencies for Lambda scraper
boto3>=1.26.0
requests>=2.28.0
beautifulsoup4>=4.11.0
lxml>=4.9.0
aiohttp>=3.8.0
asyncio>=3.4.3

# Optional dependencies (only if available)
# scrapy>=2.7.0  # May be too large for Lambda
# playwright>=1.28.0  # Too large for Lambda - disabled
EOF

# Install dependencies
print_status "Installing Lambda dependencies..."
if [ -f "${REQUIREMENTS_FILE}" ]; then
    print_status "Installing from main requirements.txt..."
    pip3 install -r "${REQUIREMENTS_FILE}" -t "${LAMBDA_DIR}/package" --quiet
fi

# Install Lambda-specific requirements
pip3 install -r "${LAMBDA_DIR}/temp/requirements_lambda.txt" -t "${LAMBDA_DIR}/package" --quiet 2>/dev/null || {
    print_warning "Some dependencies could not be installed. This is normal for Lambda environment."
}

# Copy source code to package
print_status "Packaging source code..."
cp -r "${LAMBDA_DIR}/temp"/* "${LAMBDA_DIR}/package/"

# Remove unnecessary files to reduce package size
print_status "Optimizing package size..."
cd "${LAMBDA_DIR}/package"

# Remove unnecessary files
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type f -name "*.dist-info" -delete 2>/dev/null || true

# Remove test files and documentation
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.md" -delete 2>/dev/null || true
find . -type f -name "*.txt" -delete 2>/dev/null || true
find . -type f -name "*.rst" -delete 2>/dev/null || true

# Remove large unnecessary packages if they exist
rm -rf boto3* botocore* 2>/dev/null || true  # AWS provides these in Lambda
rm -rf pytest* 2>/dev/null || true
rm -rf wheel* 2>/dev/null || true

cd - > /dev/null

# Create deployment package
print_status "Creating deployment ZIP package..."
cd "${LAMBDA_DIR}/package"
zip -r "../${FUNCTION_NAME}.zip" . -q
cd - > /dev/null

# Get package size
PACKAGE_SIZE=$(stat -f%z "${ZIP_FILE}" 2>/dev/null || stat -c%s "${ZIP_FILE}" 2>/dev/null || echo "unknown")
if [ "$PACKAGE_SIZE" != "unknown" ]; then
    PACKAGE_SIZE_MB=$((PACKAGE_SIZE / 1024 / 1024))
    print_status "Package size: ${PACKAGE_SIZE_MB}MB"
    
    if [ $PACKAGE_SIZE_MB -gt 250 ]; then
        print_warning "Package size is large (${PACKAGE_SIZE_MB}MB). Consider optimizing dependencies."
    fi
fi

print_status "Lambda package created: ${ZIP_FILE} ✅"

# Deploy using AWS CLI (optional - can also be done via Terraform)
if [ "${DEPLOY_DIRECT}" == "true" ]; then
    print_status "Deploying Lambda function directly..."
    
    # Check if function exists
    if aws lambda get-function --function-name "neuronews-news-scraper-${ENVIRONMENT}" --region "${AWS_REGION}" >/dev/null 2>&1; then
        print_status "Updating existing Lambda function..."
        aws lambda update-function-code \
            --function-name "neuronews-news-scraper-${ENVIRONMENT}" \
            --zip-file "fileb://${ZIP_FILE}" \
            --region "${AWS_REGION}"
    else
        print_warning "Lambda function does not exist. Please deploy using Terraform first."
    fi
else
    print_status "Package ready for Terraform deployment."
    print_status "Run 'terraform apply' to deploy the Lambda function."
fi

# Clean up temporary files
print_status "Cleaning up temporary files..."
rm -rf "${LAMBDA_DIR}/temp"
rm -rf "${LAMBDA_DIR}/package"

# Deployment verification script
print_status "Creating deployment verification script..."
cat > "${LAMBDA_DIR}/verify_deployment.py" << 'EOF'
#!/usr/bin/env python3
"""
Deployment verification script for NeuroNews Lambda function.
"""

import boto3
import json
import sys
import os
from datetime import datetime

def verify_lambda_deployment():
    """Verify Lambda function deployment and test invocation."""
    
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    environment = os.environ.get('ENVIRONMENT', 'dev')
    function_name = f"neuronews-news-scraper-{environment}"
    
    print(f"🔍 Verifying Lambda deployment...")
    print(f"Function: {function_name}")
    print(f"Region: {aws_region}")
    print()
    
    try:
        # Initialize Lambda client
        lambda_client = boto3.client('lambda', region_name=aws_region)
        
        # Get function configuration
        print("📋 Checking function configuration...")
        response = lambda_client.get_function(FunctionName=function_name)
        
        config = response['Configuration']
        print(f"✅ Function exists: {config['FunctionName']}")
        print(f"✅ Runtime: {config['Runtime']}")
        print(f"✅ Memory: {config['MemorySize']}MB")
        print(f"✅ Timeout: {config['Timeout']}s")
        print(f"✅ Last Modified: {config['LastModified']}")
        print()
        
        # Test invocation
        print("🧪 Testing function invocation...")
        test_event = {
            'sources': ['bbc'],
            'max_articles_per_source': 2,
            'scraper_config': {
                'concurrent_requests': 1,
                'timeout': 10
            }
        }
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(test_event)
        )
        
        if response['StatusCode'] == 200:
            payload = json.loads(response['Payload'].read())
            print("✅ Function invocation successful!")
            print(f"✅ Status Code: {payload.get('statusCode', 'N/A')}")
            
            if 'body' in payload:
                body = payload['body']
                print(f"✅ Execution Status: {body.get('status', 'N/A')}")
                print(f"✅ Execution Time: {body.get('execution_time_seconds', 'N/A')}s")
                
                if 'scraper_results' in body:
                    results = body['scraper_results']
                    print(f"✅ Articles Scraped: {results.get('total_articles', 'N/A')}")
            
        else:
            print(f"❌ Function invocation failed with status: {response['StatusCode']}")
            
    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")
        return False
    
    print()
    print("🎉 Lambda deployment verification completed!")
    return True

if __name__ == "__main__":
    success = verify_lambda_deployment()
    sys.exit(0 if success else 1)
EOF

chmod +x "${LAMBDA_DIR}/verify_deployment.py"

# Summary
echo ""
echo -e "${GREEN}🎉 Deployment preparation completed successfully!${NC}"
echo ""
echo -e "${BLUE}📋 Summary:${NC}"
echo "  ✅ Lambda package created: ${ZIP_FILE}"
echo "  ✅ Verification script: ${LAMBDA_DIR}/verify_deployment.py"
echo ""
echo -e "${BLUE}🚀 Next Steps:${NC}"
echo "  1. Deploy infrastructure: terraform apply"
echo "  2. Verify deployment: python3 ${LAMBDA_DIR}/verify_deployment.py"
echo "  3. Test EventBridge trigger: aws events put-events ..."
echo ""
echo -e "${BLUE}📖 Useful Commands:${NC}"
echo "  # Direct deployment (if needed):"
echo "  export DEPLOY_DIRECT=true && $0"
echo ""
echo "  # Update function code:"
echo "  aws lambda update-function-code \\"
echo "    --function-name neuronews-news-scraper-${ENVIRONMENT} \\"
echo "    --zip-file fileb://${ZIP_FILE}"
echo ""
echo "  # Test function:"
echo "  aws lambda invoke \\"
echo "    --function-name neuronews-news-scraper-${ENVIRONMENT} \\"
echo "    --payload '{\"sources\":[\"bbc\"],\"max_articles_per_source\":2}' \\"
echo "    response.json"
echo ""
echo -e "${GREEN}✨ Happy deploying!${NC}"
