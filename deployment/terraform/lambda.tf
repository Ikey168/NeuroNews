# AWS Lambda Functions for NeuroNews Serverless Processing

# Create an S3 bucket for Lambda function code
resource "aws_s3_bucket" "lambda_code" {
  bucket = "${var.bucket_name_prefix}-lambda-code-${var.environment}"
  
  tags = merge(
    var.tags,
    {
      Name        = "NeuroNews Lambda Code"
      Environment = var.environment
    }
  )
}

# Enable versioning for the bucket
resource "aws_s3_bucket_versioning" "lambda_code_versioning" {
  bucket = aws_s3_bucket.lambda_code.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# Enable server-side encryption for the bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "lambda_code_encryption" {
  bucket = aws_s3_bucket.lambda_code.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access to the bucket
resource "aws_s3_bucket_public_access_block" "lambda_code_public_access_block" {
  bucket = aws_s3_bucket.lambda_code.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Create a custom policy for Lambda to write to S3
resource "aws_iam_policy" "lambda_s3_write" {
  name        = "${var.lambda_function_prefix}-${var.environment}-s3-write"
  description = "Allow Lambda to write to S3 buckets"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Effect = "Allow"
        Resource = [
          "${aws_s3_bucket.raw_articles.arn}/*",
          "${aws_s3_bucket.neptune_load.arn}/*"
        ]
      }
    ]
  })
}

# Attach the custom S3 write policy to the IAM role
resource "aws_iam_role_policy_attachment" "lambda_s3_write" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_s3_write.arn
}

# Create a dummy Lambda function code file for article processing
resource "local_file" "article_processor_code" {
  content = <<EOF
import json
import boto3
import os

def lambda_handler(event, context):
    """
    Process articles from S3 and store results in Redshift.
    
    This is a dummy implementation for Terraform deployment.
    In a real implementation, this would:
    1. Read article data from S3
    2. Process the text (NLP, entity extraction, etc.)
    3. Store results in Redshift
    """
    print("Processing article...")
    
    # Dummy implementation
    return {
        'statusCode': 200,
        'body': json.dumps('Article processed successfully!')
    }
EOF

  filename = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/article_processor.py"
}

# Create a dummy Lambda function code file for knowledge graph generation
resource "local_file" "knowledge_graph_generator_code" {
  content = <<EOF
import json
import boto3
import os

def lambda_handler(event, context):
    """
    Generate knowledge graphs from processed articles and store in Neptune.
    
    This is a dummy implementation for Terraform deployment.
    In a real implementation, this would:
    1. Read processed article data from Redshift
    2. Extract entities and relationships
    3. Generate knowledge graph data
    4. Store in Neptune
    """
    print("Generating knowledge graph...")
    
    # Dummy implementation
    return {
        'statusCode': 200,
        'body': json.dumps('Knowledge graph generated successfully!')
    }
EOF

  filename = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/knowledge_graph_generator.py"
}

# Create a dummy Lambda function code file for article notification
resource "local_file" "article_notifier_code" {
  content = <<EOF
import json
import boto3
import os

def lambda_handler(event, context):
    """
    Send notifications when new articles are available.
    
    This is a dummy implementation for Terraform deployment.
    In a real implementation, this would:
    1. Read new articles
    2. Format notification message
    3. Send via SNS/SQS/etc.
    """
    print("Sending notification...")
    
    # Dummy implementation
    return {
        'statusCode': 200,
        'body': json.dumps('Notification sent successfully!')
    }
EOF

  filename = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/article_notifier.py"
}

# Create zip files for Lambda functions
data "archive_file" "article_processor_zip" {
  type        = "zip"
  source_file = local_file.article_processor_code.filename
  output_path = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/article_processor.zip"
  
  depends_on = [local_file.article_processor_code]
}

data "archive_file" "knowledge_graph_generator_zip" {
  type        = "zip"
  source_file = local_file.knowledge_graph_generator_code.filename
  output_path = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/knowledge_graph_generator.zip"
  
  depends_on = [local_file.knowledge_graph_generator_code]
}

data "archive_file" "article_notifier_zip" {
  type        = "zip"
  source_file = local_file.article_notifier_code.filename
  output_path = "/home/claude/Desktop/projects/NeuroNews/deployment/terraform/lambda_functions/article_notifier.zip"
  
  depends_on = [local_file.article_notifier_code]
}

# Upload Lambda function code to S3
resource "aws_s3_object" "article_processor_code" {
  bucket = aws_s3_bucket.lambda_code.id
  key    = "${var.lambda_s3_key_prefix}/article_processor.zip"
  source = data.archive_file.article_processor_zip.output_path
  etag   = filemd5(data.archive_file.article_processor_zip.output_path)
}

resource "aws_s3_object" "knowledge_graph_generator_code" {
  bucket = aws_s3_bucket.lambda_code.id
  key    = "${var.lambda_s3_key_prefix}/knowledge_graph_generator.zip"
  source = data.archive_file.knowledge_graph_generator_zip.output_path
  etag   = filemd5(data.archive_file.knowledge_graph_generator_zip.output_path)
}

resource "aws_s3_object" "article_notifier_code" {
  bucket = aws_s3_bucket.lambda_code.id
  key    = "${var.lambda_s3_key_prefix}/article_notifier.zip"
  source = data.archive_file.article_notifier_zip.output_path
  etag   = filemd5(data.archive_file.article_notifier_zip.output_path)
}

# Create Lambda functions
resource "aws_lambda_function" "article_processor" {
  function_name = "${var.lambda_function_prefix}-article-processor-${var.environment}"
  description   = "Process articles from S3 and store results in Redshift"
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "article_processor.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  
  s3_bucket     = aws_s3_bucket.lambda_code.id
  s3_key        = aws_s3_object.article_processor_code.key
  
  environment {
    variables = {
      ENVIRONMENT = var.environment
      REDSHIFT_CLUSTER_ENDPOINT = aws_redshift_cluster.processed_texts.endpoint
      REDSHIFT_DATABASE_NAME = aws_redshift_cluster.processed_texts.database_name
      REDSHIFT_PORT = aws_redshift_cluster.processed_texts.port
      RAW_ARTICLES_BUCKET = aws_s3_bucket.raw_articles.bucket
    }
  }
  
  reserved_concurrent_executions = var.lambda_concurrent_executions
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-article-processor-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_lambda_function" "knowledge_graph_generator" {
  function_name = "${var.lambda_function_prefix}-knowledge-graph-generator-${var.environment}"
  description   = "Generate knowledge graphs from processed articles and store in Neptune"
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "knowledge_graph_generator.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  
  s3_bucket     = aws_s3_bucket.lambda_code.id
  s3_key        = aws_s3_object.knowledge_graph_generator_code.key
  
  environment {
    variables = {
      ENVIRONMENT = var.environment
      REDSHIFT_CLUSTER_ENDPOINT = aws_redshift_cluster.processed_texts.endpoint
      REDSHIFT_DATABASE_NAME = aws_redshift_cluster.processed_texts.database_name
      REDSHIFT_PORT = aws_redshift_cluster.processed_texts.port
      NEPTUNE_ENDPOINT = aws_neptune_cluster.knowledge_graphs.endpoint
      NEPTUNE_PORT = aws_neptune_cluster.knowledge_graphs.port
      NEPTUNE_LOAD_BUCKET = aws_s3_bucket.neptune_load.bucket
    }
  }
  
  reserved_concurrent_executions = var.lambda_concurrent_executions
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-knowledge-graph-generator-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_lambda_function" "article_notifier" {
  function_name = "${var.lambda_function_prefix}-article-notifier-${var.environment}"
  description   = "Send notifications when new articles are available"
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "article_notifier.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  
  s3_bucket     = aws_s3_bucket.lambda_code.id
  s3_key        = aws_s3_object.article_notifier_code.key
  
  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }
  
  reserved_concurrent_executions = var.lambda_concurrent_executions
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-article-notifier-${var.environment}"
      Environment = var.environment
    }
  )
}

# Create CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "article_processor_logs" {
  name              = "/aws/lambda/${aws_lambda_function.article_processor.function_name}"
  retention_in_days = var.lambda_log_retention_days
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-article-processor-logs-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_cloudwatch_log_group" "knowledge_graph_generator_logs" {
  name              = "/aws/lambda/${aws_lambda_function.knowledge_graph_generator.function_name}"
  retention_in_days = var.lambda_log_retention_days
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-knowledge-graph-generator-logs-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_cloudwatch_log_group" "article_notifier_logs" {
  name              = "/aws/lambda/${aws_lambda_function.article_notifier.function_name}"
  retention_in_days = var.lambda_log_retention_days
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-article-notifier-logs-${var.environment}"
      Environment = var.environment
    }
  )
}

# Set up event triggers
resource "aws_s3_bucket_notification" "raw_articles_notification" {
  bucket = aws_s3_bucket.raw_articles.id
  
  lambda_function {
    lambda_function_arn = aws_lambda_function.article_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "articles/"
    filter_suffix       = ".json"
  }
  
  depends_on = [aws_lambda_permission.allow_s3_invoke_article_processor]
}

resource "aws_lambda_permission" "allow_s3_invoke_article_processor" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.article_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_articles.arn
}

resource "aws_cloudwatch_event_rule" "knowledge_graph_generator_rule" {
  name                = "${var.lambda_function_prefix}-knowledge-graph-generator-rule-${var.environment}"
  description         = "Trigger knowledge graph generator Lambda function on a schedule"
  schedule_expression = "rate(1 hour)"
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.lambda_function_prefix}-knowledge-graph-generator-rule-${var.environment}"
      Environment = var.environment
    }
  )
}

resource "aws_cloudwatch_event_target" "knowledge_graph_generator_target" {
  rule      = aws_cloudwatch_event_rule.knowledge_graph_generator_rule.name
  target_id = "KnowledgeGraphGeneratorTarget"
  arn       = aws_lambda_function.knowledge_graph_generator.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_invoke_knowledge_graph_generator" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.knowledge_graph_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.knowledge_graph_generator_rule.arn
}
