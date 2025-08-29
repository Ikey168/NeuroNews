"""
AWS Lambda handler for NeuroNews API.

This module provides the Lambda handler function that serves as the entry point
for AWS Lambda deployments of the NeuroNews FastAPI application.
"""

import json
import logging
from typing import Any, Dict, Optional

from mangum import Mangum

from .app import app

# Configure logging for Lambda environment
logger = logging.getLogger(__name__)

# Create Mangum handler for FastAPI app
handler = Mangum(app)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.
    
    This function serves as the main entry point for AWS Lambda deployments.
    It processes Lambda events and returns properly formatted responses.
    
    Args:
        event: AWS Lambda event dictionary containing request information
        context: AWS Lambda context object with runtime information
        
    Returns:
        Dict containing the HTTP response with statusCode, headers, and body
        
    Raises:
        ValueError: If event structure is invalid
        Exception: For any other processing errors
    """
    try:
        # Validate event structure
        if not isinstance(event, dict):
            raise ValueError("Event must be a dictionary")
            
        # Log incoming request for debugging
        logger.info(f"Processing Lambda event: {event.get('httpMethod', 'UNKNOWN')} {event.get('path', 'UNKNOWN')}")
        
        # Handle different event types
        if 'httpMethod' not in event:
            # Handle non-HTTP events (like scheduled events, SQS, etc.)
            return handle_non_http_event(event, context)
            
        # Process HTTP events through Mangum
        response = handler(event, context)
        
        # Ensure response has required structure
        if not isinstance(response, dict):
            raise ValueError("Handler response must be a dictionary")
            
        # Validate response structure
        required_keys = ['statusCode', 'body']
        for key in required_keys:
            if key not in response:
                raise ValueError(f"Response missing required key: {key}")
                
        # Ensure headers exist
        if 'headers' not in response:
            response['headers'] = {}
            
        # Add standard headers
        response['headers'].update({
            'Content-Type': 'application/json',
            'X-Powered-By': 'NeuroNews-Lambda'
        })
        
        logger.info(f"Lambda response: {response['statusCode']}")
        return response
        
    except ValueError as e:
        logger.error(f"Validation error in lambda_handler: {str(e)}")
        return create_error_response(400, f"Bad Request: {str(e)}")
        
    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}")
        return create_error_response(500, "Internal Server Error")


def handle_non_http_event(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle non-HTTP Lambda events (scheduled events, SQS, etc.).
    
    Args:
        event: Lambda event dictionary
        context: Lambda context object
        
    Returns:
        Dict containing the response
    """
    try:
        # Check for scheduled event
        if 'source' in event and event['source'] == 'aws.events':
            logger.info("Processing scheduled event")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Scheduled event processed successfully'})
            }
            
        # Check for SQS event
        if 'Records' in event:
            logger.info(f"Processing {len(event['Records'])} records")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': f"Processed {len(event['Records'])} records"})
            }
            
        # Unknown event type
        logger.warning(f"Unknown event type: {event}")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Event processed', 'type': 'unknown'})
        }
        
    except Exception as e:
        logger.error(f"Error handling non-HTTP event: {str(e)}")
        return create_error_response(500, "Error processing event")


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        Dict containing the error response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'X-Powered-By': 'NeuroNews-Lambda'
        },
        'body': json.dumps({
            'error': message,
            'statusCode': status_code
        })
    }
