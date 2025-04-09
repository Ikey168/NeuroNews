# AWS IAM Roles and Permissions for NeuroNews

# Create an IAM role for EC2 instances (for potential future use)
resource "aws_iam_role" "ec2_role" {
  name = "${var.bucket_name_prefix}-${var.environment}-ec2-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-ec2-role"
      Environment = var.environment
    }
  )
}

# Create an IAM instance profile for EC2 instances
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.bucket_name_prefix}-${var.environment}-ec2-profile"
  role = aws_iam_role.ec2_role.name
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-ec2-profile"
      Environment = var.environment
    }
  )
}

# Attach the AmazonS3ReadOnlyAccess policy to the EC2 role
resource "aws_iam_role_policy_attachment" "ec2_s3_read" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create a custom policy for EC2 to write to S3
resource "aws_iam_policy" "ec2_s3_write" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ec2-s3-write"
  description = "Allow EC2 to write to S3 buckets"
  
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
          "${aws_s3_bucket.neptune_load.arn}/*",
          "${aws_s3_bucket.lambda_code.arn}/*"
        ]
      }
    ]
  })
}

# Attach the custom S3 write policy to the EC2 role
resource "aws_iam_role_policy_attachment" "ec2_s3_write" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_s3_write.arn
}

# Create a custom policy for EC2 to access Redshift
resource "aws_iam_policy" "ec2_redshift_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ec2-redshift-access"
  description = "Allow EC2 to access Redshift"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "redshift:DescribeClusters",
          "redshift:GetClusterCredentials",
          "redshift-data:ExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the Redshift access policy to the EC2 role
resource "aws_iam_role_policy_attachment" "ec2_redshift_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_redshift_access.arn
}

# Create a custom policy for EC2 to access Neptune
resource "aws_iam_policy" "ec2_neptune_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ec2-neptune-access"
  description = "Allow EC2 to access Neptune"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "neptune-db:*"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the Neptune access policy to the EC2 role
resource "aws_iam_role_policy_attachment" "ec2_neptune_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_neptune_access.arn
}

# Create an IAM role for ECS tasks (for potential future use)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.bucket_name_prefix}-${var.environment}-ecs-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-ecs-task-role"
      Environment = var.environment
    }
  )
}

# Create an IAM role for ECS task execution
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.bucket_name_prefix}-${var.environment}-ecs-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-ecs-execution-role"
      Environment = var.environment
    }
  )
}

# Attach the AmazonECSTaskExecutionRolePolicy to the ECS execution role
resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Attach the AmazonS3ReadOnlyAccess policy to the ECS task role
resource "aws_iam_role_policy_attachment" "ecs_s3_read" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create a custom policy for ECS to write to S3
resource "aws_iam_policy" "ecs_s3_write" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ecs-s3-write"
  description = "Allow ECS to write to S3 buckets"
  
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

# Attach the custom S3 write policy to the ECS task role
resource "aws_iam_role_policy_attachment" "ecs_s3_write" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_s3_write.arn
}

# Create a custom policy for ECS to access Redshift
resource "aws_iam_policy" "ecs_redshift_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ecs-redshift-access"
  description = "Allow ECS to access Redshift"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "redshift:DescribeClusters",
          "redshift:GetClusterCredentials",
          "redshift-data:ExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the Redshift access policy to the ECS task role
resource "aws_iam_role_policy_attachment" "ecs_redshift_access" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_redshift_access.arn
}

# Create a custom policy for ECS to access Neptune
resource "aws_iam_policy" "ecs_neptune_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ecs-neptune-access"
  description = "Allow ECS to access Neptune"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "neptune-db:*"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the Neptune access policy to the ECS task role
resource "aws_iam_role_policy_attachment" "ecs_neptune_access" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_neptune_access.arn
}

# Create an IAM user for CI/CD
resource "aws_iam_user" "cicd_user" {
  name = "${var.bucket_name_prefix}-${var.environment}-cicd-user"
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-cicd-user"
      Environment = var.environment
    }
  )
}

# Create an IAM policy for CI/CD
resource "aws_iam_policy" "cicd_policy" {
  name        = "${var.bucket_name_prefix}-${var.environment}-cicd-policy"
  description = "Policy for CI/CD to deploy to AWS"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.lambda_code.arn,
          "${aws_s3_bucket.lambda_code.arn}/*"
        ]
      },
      {
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:UpdateFunctionConfiguration"
        ]
        Effect = "Allow"
        Resource = [
          aws_lambda_function.article_processor.arn,
          aws_lambda_function.knowledge_graph_generator.arn,
          aws_lambda_function.article_notifier.arn
        ]
      }
    ]
  })
}

# Attach the CI/CD policy to the CI/CD user
resource "aws_iam_user_policy_attachment" "cicd_policy_attachment" {
  user       = aws_iam_user.cicd_user.name
  policy_arn = aws_iam_policy.cicd_policy.arn
}

# Create an IAM group for developers
resource "aws_iam_group" "developers" {
  name = "${var.bucket_name_prefix}-${var.environment}-developers"
}

# Create an IAM policy for developers
resource "aws_iam_policy" "developer_policy" {
  name        = "${var.bucket_name_prefix}-${var.environment}-developer-policy"
  description = "Policy for developers to access AWS resources"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:ListBucket",
          "s3:GetObject"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.raw_articles.arn,
          "${aws_s3_bucket.raw_articles.arn}/*",
          aws_s3_bucket.neptune_load.arn,
          "${aws_s3_bucket.neptune_load.arn}/*",
          aws_s3_bucket.lambda_code.arn,
          "${aws_s3_bucket.lambda_code.arn}/*"
        ]
      },
      {
        Action = [
          "lambda:GetFunction",
          "lambda:ListFunctions",
          "lambda:GetFunctionConfiguration",
          "lambda:InvokeFunction"
        ]
        Effect = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "redshift:DescribeClusters",
          "redshift-data:ExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult"
        ]
        Effect = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "neptune-db:ReadDataViaQuery",
          "neptune-db:GetQueryStatus",
          "neptune-db:CancelQuery"
        ]
        Effect = "Allow"
        Resource = "*"
      },
      {
        Action = [
          "cloudwatch:GetMetricData",
          "cloudwatch:ListMetrics",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:GetLogEvents"
        ]
        Effect = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the developer policy to the developers group
resource "aws_iam_group_policy_attachment" "developer_policy_attachment" {
  group      = aws_iam_group.developers.name
  policy_arn = aws_iam_policy.developer_policy.arn
}

# Create an IAM group for administrators
resource "aws_iam_group" "administrators" {
  name = "${var.bucket_name_prefix}-${var.environment}-administrators"
}

# Attach the AdministratorAccess policy to the administrators group
resource "aws_iam_group_policy_attachment" "administrator_policy_attachment" {
  group      = aws_iam_group.administrators.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# Create an IAM role for cross-account access (for potential future use)
resource "aws_iam_role" "cross_account_role" {
  name = "${var.bucket_name_prefix}-${var.environment}-cross-account-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.trusted_account_id}:root"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-cross-account-role"
      Environment = var.environment
    }
  )
}

# Create a custom policy for cross-account access
resource "aws_iam_policy" "cross_account_policy" {
  name        = "${var.bucket_name_prefix}-${var.environment}-cross-account-policy"
  description = "Policy for cross-account access"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:ListBucket",
          "s3:GetObject"
        ]
        Effect = "Allow"
        Resource = [
          aws_s3_bucket.raw_articles.arn,
          "${aws_s3_bucket.raw_articles.arn}/*"
        ]
      },
      {
        Action = [
          "redshift:DescribeClusters",
          "redshift-data:ExecuteStatement",
          "redshift-data:DescribeStatement",
          "redshift-data:GetStatementResult"
        ]
        Effect = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the cross-account policy to the cross-account role
resource "aws_iam_role_policy_attachment" "cross_account_policy_attachment" {
  role       = aws_iam_role.cross_account_role.name
  policy_arn = aws_iam_policy.cross_account_policy.arn
}

# Create an IAM user for the scraper
resource "aws_iam_user" "scraper_user" {
  name = "${var.bucket_name_prefix}-${var.environment}-scraper"
  
  tags = merge(
    var.tags,
    {
      Name        = "${var.bucket_name_prefix}-${var.environment}-scraper"
      Environment = var.environment
      Purpose     = "News article scraping"
    }
  )
}

# Create a policy for the scraper
resource "aws_iam_policy" "scraper_policy" {
  name        = "${var.bucket_name_prefix}-${var.environment}-scraper-policy"
  description = "Policy for the news scraper to store articles and logs"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw_articles.arn,
          "${aws_s3_bucket.raw_articles.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          "arn:aws:logs:*:*:log-group:${var.bucket_name_prefix}-${var.environment}-scraper:*"
        ]
      }
    ]
  })
}

# Attach the policy to the scraper user
resource "aws_iam_user_policy_attachment" "scraper_policy_attachment" {
  user       = aws_iam_user.scraper_user.name
  policy_arn = aws_iam_policy.scraper_policy.arn
}
