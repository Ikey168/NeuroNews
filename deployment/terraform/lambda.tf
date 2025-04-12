# Lambda Function Configuration for NeuroNews

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

  environment {
    variables = {
      S3_BUCKET = module.s3.raw_articles_bucket_name
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = "Article Processor Lambda Function",
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

  environment {
    variables = {
      S3_BUCKET = module.s3.raw_articles_bucket_name
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = "Knowledge Graph Generator Lambda Function",
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

  tags = merge(
    var.tags,
    {
      Name        = "Article Notifier Lambda Function",
      Environment = var.environment
    }
  )
}

resource "aws_lambda_permission" "allow_s3_invoke_article_processor" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.article_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3.raw_articles_bucket_arn
}

resource "aws_cloudwatch_log_group" "article_processor_logs" {
  name              = "/aws/lambda/${aws_lambda_function.article_processor.function_name}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_cloudwatch_log_group" "knowledge_graph_generator_logs" {
  name              = "/aws/lambda/${aws_lambda_function.knowledge_graph_generator.function_name}"
  retention_in_days = var.lambda_log_retention_days
}

resource "aws_cloudwatch_log_group" "article_notifier_logs" {
  name              = "/aws/lambda/${aws_lambda_function.article_notifier.function_name}"
  retention_in_days = var.lambda_log_retention_days
}
