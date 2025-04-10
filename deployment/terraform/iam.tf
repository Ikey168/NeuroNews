# IAM Configuration for NeuroNews

# Create a group for administrators
resource "aws_iam_group" "administrators" {
  count = var.create_admin_group ? 1 : 0
  name  = "${var.bucket_name_prefix}-${var.environment}-administrators"
}

# Create a group for developers
resource "aws_iam_group" "developers" {
  count = var.create_developer_group ? 1 : 0
  name  = "${var.bucket_name_prefix}-${var.environment}-developers"
}

# Create a CI/CD user
resource "aws_iam_user" "cicd_user" {
  count = var.create_cicd_user ? 1 : 0
  name  = "${var.bucket_name_prefix}-${var.environment}-cicd-user"
}

# Create a user for the scraper
resource "aws_iam_user" "scraper_user" {
  name = "${var.bucket_name_prefix}-${var.environment}-scraper"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_user_tags" "scraper_user" {
  name = aws_iam_user.scraper_user.name

  tags = merge(
    var.tags,
    {
      Name        = "Scraper User"
      Environment = var.environment
    }
  )
}

# Attach Administrator policy to administrators group
resource "aws_iam_group_policy_attachment" "administrator_policy_attachment" {
  count      = var.create_admin_group ? 1 : 0
  group      = aws_iam_group.administrators[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# Create cross-account role (if enabled)
resource "aws_iam_role" "cross_account_role" {
  count = (var.create_cross_account_role && var.trusted_account_id != "") ? 1 : 0
  name  = "${var.bucket_name_prefix}-${var.environment}-cross-account-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = var.trusted_account_id != "" ? "arn:aws:iam::${var.trusted_account_id}:root" : null
        }
        Condition = {}
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "Cross Account Role"
      Environment = var.environment
    }
  )
}

# Create Lambda execution role
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

# Create policy for Lambda to access Neptune
resource "aws_iam_policy" "lambda_neptune_access" {
  name        = "${var.lambda_function_prefix}-${var.environment}-neptune-access"
  description = "Allow Lambda functions to access Neptune database"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Neptune access policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_neptune_access" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_neptune_access.arn
}

# Create policy for Lambda to access Redshift
resource "aws_iam_policy" "lambda_redshift_access" {
  name        = "${var.lambda_function_prefix}-${var.environment}-redshift-access"
  description = "Allow Lambda functions to access Redshift cluster"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "redshift:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Redshift access policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_redshift_access" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = aws_iam_policy.lambda_redshift_access.arn
}

# Create EC2 role for running the scraper
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
      Name        = "EC2 Role"
      Environment = var.environment
    }
  )
}

# Create EC2 instance profile
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.bucket_name_prefix}-${var.environment}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# Attach S3 read policy to EC2 role
resource "aws_iam_role_policy_attachment" "ec2_s3_read" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create policy for EC2 to access Neptune
resource "aws_iam_policy" "ec2_neptune_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ec2-neptune-access"
  description = "Allow EC2 instances to access Neptune database"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Neptune access policy to EC2 role
resource "aws_iam_role_policy_attachment" "ec2_neptune_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_neptune_access.arn
}

# Create policy for EC2 to access Redshift
resource "aws_iam_policy" "ec2_redshift_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ec2-redshift-access"
  description = "Allow EC2 instances to access Redshift cluster"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "redshift:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Redshift access policy to EC2 role
resource "aws_iam_role_policy_attachment" "ec2_redshift_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_redshift_access.arn
}

# Create ECS execution role
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
      Name        = "ECS Execution Role"
      Environment = var.environment
    }
  )
}

# Attach ECS task execution role policy
resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Create ECS task role
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
      Name        = "ECS Task Role"
      Environment = var.environment
    }
  )
}

# Attach S3 read policy to ECS task role
resource "aws_iam_role_policy_attachment" "ecs_s3_read" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

# Create policy for ECS tasks to access Neptune
resource "aws_iam_policy" "ecs_neptune_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ecs-neptune-access"
  description = "Allow ECS tasks to access Neptune database"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Neptune access policy to ECS task role
resource "aws_iam_role_policy_attachment" "ecs_neptune_access" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_neptune_access.arn
}

# Create policy for ECS tasks to access Redshift
resource "aws_iam_policy" "ecs_redshift_access" {
  name        = "${var.bucket_name_prefix}-${var.environment}-ecs-redshift-access"
  description = "Allow ECS tasks to access Redshift cluster"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "redshift:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach Redshift access policy to ECS task role
resource "aws_iam_role_policy_attachment" "ecs_redshift_access" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_redshift_access.arn
}

# Create role for Redshift S3 access
resource "aws_iam_role" "redshift_s3_access" {
  name = "${var.redshift_cluster_identifier}-${var.environment}-s3-access"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "redshift.amazonaws.com"
        }
      }
    ]
  })
  
  tags = merge(
    var.tags,
    {
      Name        = "Redshift S3 Access"
      Environment = var.environment
    }
  )
}

# Attach S3 read policy to Redshift role
resource "aws_iam_role_policy_attachment" "redshift_s3_access" {
  role       = aws_iam_role.redshift_s3_access.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}
