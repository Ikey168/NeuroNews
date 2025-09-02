import json


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
    return {"statusCode": 200, "body": json.dumps("Notification sent successfully!")}
