# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "lambda_scraper" {
  name              = "/aws/lambda/scraper-functions"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Service     = "scraper"
  }
}

resource "aws_cloudwatch_log_group" "ec2_scraper" {
  name              = "/aws/ec2/scrapers"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Service     = "scraper"
  }
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/neuronews"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Service     = "api"
  }
}

resource "aws_cloudwatch_log_group" "nlp_jobs" {
  name              = "/aws/batch/nlp-processing"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Service     = "nlp"
  }
}

# SNS Topic for Alerts
resource "aws_sns_topic" "pipeline_alerts" {
  name = "data-pipeline-alerts-${var.environment}"
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "NeuroNews-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["Production/DataPipeline", "ScrapeSuccess", { "stat": "Average", "period": 300 }],
            ["Production/DataPipeline", "ScrapeDuration", { "stat": "Average", "period": 300 }]
          ]
          view    = "timeSeries"
          region  = var.aws_region
          title   = "Scraper Performance"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/ApiGateway", "4XXError", { "stat": "Sum", "period": 300 }],
            ["AWS/ApiGateway", "5XXError", { "stat": "Sum", "period": 300 }],
            ["AWS/ApiGateway", "Latency", { "stat": "Average", "period": 300 }]
          ]
          view    = "timeSeries"
          region  = var.aws_region
          title   = "API Health"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["Production/DataPipeline", "NLPJobsCompleted", { "stat": "Sum", "period": 300 }],
            ["Production/DataPipeline", "NLPProcessingTime", { "stat": "Average", "period": 300 }]
          ]
          view    = "timeSeries"
          region  = var.aws_region
          title   = "NLP Performance"
          period  = 300
        }
      }
    ]
  })
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "scraper_failures" {
  alarm_name          = "scraper-consecutive-failures-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ScrapeFailures"
  namespace           = "Production/DataPipeline"
  period             = 300
  statistic          = "Sum"
  threshold          = 0
  alarm_description  = "This metric monitors consecutive scraper failures"
  alarm_actions      = [aws_sns_topic.pipeline_alerts.arn]

  dimensions = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "api_error_rate" {
  alarm_name          = "api-error-rate-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period             = 300
  statistic          = "Average"
  threshold          = 5
  alarm_description  = "This metric monitors API error rate"
  alarm_actions      = [aws_sns_topic.pipeline_alerts.arn]

  dimensions = {
    Environment = var.environment
  }
}

resource "aws_cloudwatch_metric_alarm" "nlp_processing_time" {
  alarm_name          = "nlp-processing-time-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "NLPProcessingTime"
  namespace           = "Production/DataPipeline"
  period             = 300
  statistic          = "Average"
  threshold          = 1800  # 30 minutes in seconds
  alarm_description  = "This metric monitors NLP job processing time"
  alarm_actions      = [aws_sns_topic.pipeline_alerts.arn]

  dimensions = {
    Environment = var.environment
  }
}

# IAM role for CloudWatch agent on EC2
resource "aws_iam_role" "cloudwatch_agent" {
  name = "cloudwatch-agent-role-${var.environment}"

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
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.cloudwatch_agent.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}