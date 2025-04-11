# Lambda Function Configuration for NeuroNews

# Create IAM role for Lambda functions
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.lambda_function_prefix}-${var.environment}-lambda-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "Lambda Execution Role"
      Environment = var.environment
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach S3 read policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_s3_read" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create policy for Lambda to write to S3
resource "aws_iam_policy" "lambda_s3_write" {
  name        = "${var.lambda_function_prefix}-${var.environment}-s3-write"
  description = "Allow Lambda functions to write to S3 bucket"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = [
          "${aws_s3_bucket.raw_articles.arn}/*",
#          "${aws_s3_bucket.neptune_load.arn}/*"
        ]
      }
    ]
  })
}

# Attach S3 write policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_s3_write" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_s3_write.arn
}

# Create policy for Lambda to access CloudWatch Logs
resource "aws_iam_policy" "lambda_cloudwatch_logs" {
  name        = "${var.lambda_function_prefix}-${var.environment}-cloudwatch-logs"
  description = "Allow Lambda functions to write to CloudWatch Logs"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Attach CloudWatch Logs policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_cloudwatch_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_cloudwatch_logs.arn
}

# Create Lambda function for article processing
resource "aws_lambda_function" "article_processor" {
  function_name = "${var.lambda_function_prefix}-article-processor-${var.environment}"
  description   = "Processes news articles and stores them in S3"
  handler       = "article_processor.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  s3_bucket     = aws_s3_bucket.lambda_code.bucket
  s3_key        = "lambda-functions/article_processor.zip"
  role          = aws_iam_role.lambda_execution_role.arn
  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_s3_read,
    aws_iam_role_policy_attachment.lambda_cloudwatch_logs,
    aws_iam_role_policy_attachment.lambda_s3_write
  ]

  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.raw_articles.bucket
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = "Article Processor Lambda Function"
      Environment = var.environment
    }
  )
}

resource "aws_lambda_function" "knowledge_graph_generator" {
  function_name = "${var.lambda_function_prefix}-knowledge-graph-generator-${var.environment}"
  description   = "Generates knowledge graphs from processed articles and stores them in Neptune"
  handler       = "knowledge_graph_generator.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  s3_bucket     = aws_s3_bucket.lambda_code.bucket
  s3_key        = "lambda-functions/knowledge_graph_generator.zip"
  role          = aws_iam_role.lambda_execution_role.arn
  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_s3_read,
    aws_iam_role_policy_attachment.lambda_cloudwatch_logs,
    aws_iam_role_policy_attachment.lambda_s3_write
  ]

  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.raw_articles.bucket,
#      NEPTUNE_ENDPOINT = aws_neptune_cluster.knowledge_graphs.endpoint
#      NEPTUNE_PORT = aws_neptune_cluster.knowledge_graphs.port
#      NEPTUNE_LOAD_BUCKET = aws_s3_bucket.neptune_load.bucket
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = "Knowledge Graph Generator Lambda Function"
      Environment = var.environment
    }
  )
}

resource "aws_lambda_function" "article_notifier" {
  function_name = "${var.lambda_function_prefix}-article-notifier-${var.environment}"
  description   = "Sends notifications when new articles are available"
  handler       = "article_notifier.lambda_handler"
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  s3_bucket     = aws_s3_bucket.lambda_code.bucket
  s3_key        = "lambda-functions/article_notifier.zip"
  role          = aws_iam_role.lambda_execution_role.arn
  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_s3_read,
    aws_iam_role_policy_attachment.lambda_cloudwatch_logs,
    aws_iam_role_policy_attachment.lambda_s3_write
  ]

  tags = merge(
    var.tags,
    {
      Name        = "Article Notifier Lambda Function"
      Environment = var.environment
    }
  )
}

resource "aws_lambda_permission" "allow_s3_invoke_article_processor" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.article_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw_articles.arn
}

resource "aws_cloudwatch_log_group" "article_processor_logs" {
  name             = "/aws/lambda/${aws_lambda_function.article_processor.function_name}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_cloudwatch_log_group" "knowledge_graph_generator_logs" {
  name             = "/aws/lambda/${aws_lambda_function.knowledge_graph_generator.function_name}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_cloudwatch_log_group" "article_notifier_logs" {
  name             = "/aws/lambda/${aws_lambda_function.article_notifier.function_name}"
  retention_in_days = var.lambda_log_retention_days
}
