#!/usr/bin/env python3
"""
Schema Registry Publishing CLI

Registers Avro schemas to a Confluent Schema Registry compatible service.
Supports Karapace, Confluent Schema Registry, and other compatible implementations.
"""

import argparse
import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from urllib.parse import urljoin


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SchemaRegistryClient:
    """Client for interacting with Schema Registry API"""
    
    def __init__(self, base_url: str, auth: Optional[tuple] = None):
        self.base_url = base_url.rstrip('/')
        self.auth = auth
        self.session = requests.Session()
        if auth:
            self.session.auth = auth
    
    def check_health(self) -> bool:
        """Check if schema registry is accessible"""
        try:
            response = self.session.get(f"{self.base_url}/subjects")
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Schema registry health check failed: {e}")
            return False
    
    def get_schema_versions(self, subject: str) -> list:
        """Get all versions for a subject"""
        try:
            response = self.session.get(f"{self.base_url}/subjects/{subject}/versions")
            if response.status_code == 404:
                return []
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get versions for subject {subject}: {e}")
            return []
    
    def check_compatibility(self, subject: str, schema: str) -> bool:
        """Check if schema is compatible with latest version"""
        try:
            payload = {"schema": schema}
            response = self.session.post(
                f"{self.base_url}/compatibility/subjects/{subject}/versions/latest",
                json=payload,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"}
            )
            if response.status_code == 404:
                # No previous version exists, compatibility check passes
                return True
            response.raise_for_status()
            result = response.json()
            return result.get("is_compatible", False)
        except requests.RequestException as e:
            logger.error(f"Compatibility check failed for subject {subject}: {e}")
            return False
    
    def register_schema(self, subject: str, schema: str) -> Optional[Dict[str, Any]]:
        """Register a schema for a subject"""
        try:
            payload = {"schema": schema}
            response = self.session.post(
                f"{self.base_url}/subjects/{subject}/versions",
                json=payload,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to register schema for subject {subject}: {e}")
            return None


def load_avro_schema(schema_path: Path) -> Optional[str]:
    """Load and validate Avro schema from file"""
    try:
        with open(schema_path, 'r') as f:
            schema_data = json.load(f)
        
        # Basic validation - check for required Avro fields
        if not isinstance(schema_data, dict):
            raise ValueError("Schema must be a JSON object")
        
        if schema_data.get("type") != "record":
            raise ValueError("Schema must be of type 'record'")
        
        required_fields = ["name", "fields"]
        for field in required_fields:
            if field not in schema_data:
                raise ValueError(f"Schema missing required field: {field}")
        
        # Return schema as JSON string (registry expects string format)
        return json.dumps(schema_data)
        
    except Exception as e:
        logger.error(f"Failed to load schema from {schema_path}: {e}")
        return None


def determine_subject_name(schema_path: Path, subject_override: Optional[str] = None) -> str:
    """Determine subject name from schema file or override"""
    if subject_override:
        return subject_override
    
    # Default subject naming pattern: neuronews.{SchemaName}-value
    schema_name = schema_path.stem
    if schema_name.endswith('-v1'):
        schema_name = schema_name[:-3]  # Remove version suffix
    
    # Convert kebab-case to PascalCase
    pascal_name = ''.join(word.capitalize() for word in schema_name.split('-'))
    return f"neuronews.{pascal_name}-value"


def publish_schema(
    schema_path: Path,
    registry_url: str,
    subject: Optional[str] = None,
    check_compatibility: bool = True,
    dry_run: bool = False,
    auth: Optional[tuple] = None
) -> bool:
    """
    Publish an Avro schema to the registry
    
    Args:
        schema_path: Path to the Avro schema file
        registry_url: Schema registry base URL
        subject: Subject name (auto-generated if None)
        check_compatibility: Whether to check compatibility before publishing
        dry_run: If True, only validate without publishing
        auth: Optional (username, password) tuple for authentication
    
    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Publishing schema from {schema_path}")
    
    # Load schema
    schema = load_avro_schema(schema_path)
    if not schema:
        return False
    
    # Determine subject name
    subject_name = determine_subject_name(schema_path, subject)
    logger.info(f"Subject: {subject_name}")
    
    # Initialize client
    client = SchemaRegistryClient(registry_url, auth)
    
    # Check registry health
    if not client.check_health():
        logger.error("Schema registry is not accessible")
        return False
    
    # Get existing versions
    existing_versions = client.get_schema_versions(subject_name)
    logger.info(f"Existing versions for {subject_name}: {existing_versions}")
    
    # Check compatibility if requested and there are existing versions
    if check_compatibility and existing_versions:
        logger.info("Checking schema compatibility...")
        if not client.check_compatibility(subject_name, schema):
            logger.error("Schema is not compatible with existing versions")
            return False
        logger.info("Schema compatibility check passed")
    
    if dry_run:
        logger.info("Dry run mode - schema would be published successfully")
        return True
    
    # Register schema
    logger.info("Registering schema...")
    result = client.register_schema(subject_name, schema)
    
    if result:
        version = result.get("version", "unknown")
        schema_id = result.get("id", "unknown")
        logger.info(f"Schema registered successfully - Version: {version}, ID: {schema_id}")
        return True
    else:
        logger.error("Failed to register schema")
        return False


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Publish Avro schemas to Schema Registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Publish ArticleIngest schema
  python scripts/contracts/publish_schema.py contracts/schemas/avro/article-ingest-v1.avsc
  
  # Publish with custom subject name
  python scripts/contracts/publish_schema.py contracts/schemas/avro/article-ingest-v1.avsc --subject custom.subject-value
  
  # Dry run to validate without publishing
  python scripts/contracts/publish_schema.py contracts/schemas/avro/article-ingest-v1.avsc --dry-run
  
  # Use custom registry URL
  python scripts/contracts/publish_schema.py contracts/schemas/avro/article-ingest-v1.avsc --registry-url http://localhost:8081
        """
    )
    
    parser.add_argument(
        "schema_path",
        type=Path,
        help="Path to the Avro schema file (.avsc)"
    )
    
    parser.add_argument(
        "--registry-url",
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081"),
        help="Schema Registry URL (default: $SCHEMA_REGISTRY_URL or http://localhost:8081)"
    )
    
    parser.add_argument(
        "--subject",
        help="Custom subject name (default: auto-generated from schema name)"
    )
    
    parser.add_argument(
        "--skip-compatibility",
        action="store_true",
        help="Skip compatibility check before publishing"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate schema without publishing"
    )
    
    parser.add_argument(
        "--username",
        help="Registry username for authentication"
    )
    
    parser.add_argument(
        "--password",
        help="Registry password for authentication"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate schema file exists
    if not args.schema_path.exists():
        logger.error(f"Schema file not found: {args.schema_path}")
        sys.exit(1)
    
    if not args.schema_path.suffix == '.avsc':
        logger.error("Schema file must have .avsc extension")
        sys.exit(1)
    
    # Prepare authentication
    auth = None
    if args.username and args.password:
        auth = (args.username, args.password)
    elif args.username or args.password:
        logger.error("Both username and password must be provided for authentication")
        sys.exit(1)
    
    # Publish schema
    success = publish_schema(
        schema_path=args.schema_path,
        registry_url=args.registry_url,
        subject=args.subject,
        check_compatibility=not args.skip_compatibility,
        dry_run=args.dry_run,
        auth=auth
    )
    
    if success:
        logger.info("Schema publishing completed successfully")
        sys.exit(0)
    else:
        logger.error("Schema publishing failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
