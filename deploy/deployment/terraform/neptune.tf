# Neptune Security Group
resource "aws_security_group" "neptune" {
  name_prefix = "${var.environment}-neptune-"
  description = "Security group for Neptune cluster"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = var.neptune_port
    to_port     = var.neptune_port
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.environment}-neptune-sg"
  })
}

# Neptune Subnet Group
resource "aws_neptune_subnet_group" "main" {
  name        = "${var.environment}-neptune-subnet-group"
  description = "Neptune subnet group"
  subnet_ids  = aws_subnet.private[*].id

  tags = var.tags
}

# Neptune Parameter Group
resource "aws_neptune_parameter_group" "main" {
  family      = "neptune1.2"
  name        = "${var.environment}-neptune-param-group"
  description = "Neptune parameter group"

  parameter {
    name  = "neptune_enable_audit_logs"
    value = var.neptune_enable_audit_logs ? "1" : "0"
  }

  tags = var.tags
}

# Neptune Cluster
resource "aws_neptune_cluster" "main" {
  cluster_identifier                  = var.neptune_cluster_identifier
  engine                             = "neptune"
  engine_version                     = "1.2.1.0"
  neptune_cluster_parameter_group_name = aws_neptune_parameter_group.main.name
  vpc_security_group_ids            = [aws_security_group.neptune.id]
  neptune_subnet_group_name         = aws_neptune_subnet_group.main.name
  port                              = var.neptune_port
  backup_retention_period           = var.neptune_backup_retention_period
  preferred_backup_window           = var.neptune_preferred_backup_window
  skip_final_snapshot              = var.neptune_skip_final_snapshot
  iam_database_authentication_enabled = true

  tags = var.tags
}

# Neptune Instances
resource "aws_neptune_cluster_instance" "main" {
  count              = var.neptune_cluster_size
  cluster_identifier = aws_neptune_cluster.main.id
  instance_class     = var.neptune_instance_class
  engine             = "neptune"
  neptune_parameter_group_name = aws_neptune_parameter_group.main.name

  tags = var.tags

  depends_on = [aws_neptune_cluster.main]
}

# IAM Role for Neptune
resource "aws_iam_role" "neptune" {
  name = "${var.environment}-neptune-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "neptune-db.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Neptune IAM Policy
resource "aws_iam_role_policy" "neptune" {
  name = "${var.environment}-neptune-policy"
  role = aws_iam_role.neptune.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          module.s3.raw_articles_bucket_arn,
          "${module.s3.raw_articles_bucket_arn}/*"
        ]
      }
    ]
  })
}

# Lambda function to initialize Neptune schema
resource "aws_lambda_function" "init_neptune_schema" {
  filename      = "lambda_functions/knowledge_graph_generator.zip"
  function_name = "${var.environment}-init-neptune-schema"
  role         = aws_iam_role.neptune_lambda.arn
  handler      = "knowledge_graph_generator.lambda_handler"
  runtime      = var.lambda_runtime
  timeout      = 300
  memory_size  = 256

  environment {
    variables = {
      NEPTUNE_ENDPOINT = aws_neptune_cluster.main.endpoint
    }
  }

  depends_on = [aws_neptune_cluster.main]

  tags = var.tags
}

# IAM role for Lambda to access Neptune
resource "aws_iam_role" "neptune_lambda" {
  name = "${var.environment}-neptune-lambda-role"

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

  tags = var.tags
}

# IAM policy for Lambda to access Neptune
resource "aws_iam_role_policy" "neptune_lambda" {
  name = "${var.environment}-neptune-lambda-policy"
  role = aws_iam_role.neptune_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:*"
        ]
        Resource = [
          aws_neptune_cluster.main.arn,
          "${aws_neptune_cluster.main.arn}/*"
        ]
      },
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

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "init_neptune_schema" {
  name              = "/aws/lambda/${aws_lambda_function.init_neptune_schema.function_name}"
  retention_in_days = var.lambda_log_retention_days

  tags = var.tags
}

# Event rule to trigger schema initialization after cluster creation
resource "aws_cloudwatch_event_rule" "init_neptune_schema" {
  name                = "${var.environment}-init-neptune-schema"
  description         = "Trigger Neptune schema initialization after cluster creation"
  schedule_expression = "rate(1 minute)"
  state              = "ENABLED"

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "init_neptune_schema" {
  rule      = aws_cloudwatch_event_rule.init_neptune_schema.name
  target_id = "InitNeptuneSchema"
  arn      = aws_lambda_function.init_neptune_schema.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowCloudWatchInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.init_neptune_schema.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.init_neptune_schema.arn
}

# VPC Endpoint for Neptune
resource "aws_vpc_endpoint" "neptune" {
  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.${var.aws_region}.neptune-db"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.neptune.id]

  tags = merge(var.tags, {
    Name = "${var.environment}-neptune-vpce"
  })
}

# Outputs
output "neptune_cluster_endpoint" {
  description = "Neptune cluster endpoint"
  value       = aws_neptune_cluster.main.endpoint
}

output "neptune_cluster_port" {
  description = "Neptune cluster port"
  value       = aws_neptune_cluster.main.port
}

output "neptune_cluster_arn" {
  description = "Neptune cluster ARN"
  value       = aws_neptune_cluster.main.arn
}
