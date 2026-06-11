#!/usr/bin/env python3
"""
Event Validation CLI

Validates JSON data against Avro and JSON Schema specifications.
Supports batch validation of multiple files and comprehensive error reporting.
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import jsonschema
from jsonschema import validate, ValidationError
import avro.schema
import avro.io
import io


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ValidationResult:
    """Container for validation results"""
    
    def __init__(self, file_path: Path, schema_type: str):
        self.file_path = file_path
        self.schema_type = schema_type
        self.is_valid = False
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def add_error(self, error: str):
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
    
    def __str__(self):
        status = "✅ VALID" if self.is_valid else "❌ INVALID"
        result = f"{status} - {self.file_path} ({self.schema_type})"
        
        if self.errors:
            result += "\n  Errors:"
            for error in self.errors:
                result += f"\n    • {error}"
        
        if self.warnings:
            result += "\n  Warnings:"
            for warning in self.warnings:
                result += f"\n    • {warning}"
        
        return result


class SchemaValidator:
    """Base class for schema validators"""
    
    def __init__(self, schema_path: Path):
        self.schema_path = schema_path
        self.schema = self.load_schema()
    
    def load_schema(self):
        """Load schema from file - to be implemented by subclasses"""
        raise NotImplementedError
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate data against schema - to be implemented by subclasses"""
        raise NotImplementedError


class JSONSchemaValidator(SchemaValidator):
    """JSON Schema validator"""
    
    def load_schema(self):
        """Load JSON Schema from file"""
        try:
            with open(self.schema_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON Schema from {self.schema_path}: {e}")
            return None
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate data against JSON Schema"""
        result = ValidationResult(self.schema_path, "JSON Schema")
        
        if not self.schema:
            result.add_error("Schema could not be loaded")
            return result
        
        try:
            validate(instance=data, schema=self.schema)
            result.is_valid = True
            logger.debug(f"JSON Schema validation passed for {self.schema_path}")
        except ValidationError as e:
            result.add_error(f"Validation error: {e.message}")
            if e.absolute_path:
                result.add_error(f"Path: {' -> '.join(str(p) for p in e.absolute_path)}")
        except Exception as e:
            result.add_error(f"Unexpected validation error: {e}")
        
        return result


class AvroSchemaValidator(SchemaValidator):
    """Avro Schema validator"""
    
    def load_schema(self):
        """Load Avro Schema from file"""
        try:
            with open(self.schema_path, 'r') as f:
                schema_dict = json.load(f)
            return avro.schema.parse(json.dumps(schema_dict))
        except Exception as e:
            logger.error(f"Failed to load Avro Schema from {self.schema_path}: {e}")
            return None
    
    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate data against Avro Schema"""
        result = ValidationResult(self.schema_path, "Avro Schema")
        
        if not self.schema:
            result.add_error("Schema could not be loaded")
            return result
        
        try:
            # Convert data for Avro validation
            avro_data = self._prepare_avro_data(data)
            
            # Create writer and validate by attempting to serialize
            writer = avro.io.DatumWriter(self.schema)
            bytes_writer = io.BytesIO()
            encoder = avro.io.BinaryEncoder(bytes_writer)
            writer.write(avro_data, encoder)
            
            result.is_valid = True
            logger.debug(f"Avro Schema validation passed for {self.schema_path}")
            
        except Exception as e:
            result.add_error(f"Avro validation error: {e}")
        
        return result
    
    def _prepare_avro_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for Avro validation by handling type conversions"""
        # Create a copy to avoid modifying original data
        avro_data = data.copy()
        
        # Handle timestamp fields - convert ISO strings to milliseconds
        timestamp_fields = ['published_at', 'ingested_at']
        for field in timestamp_fields:
            if field in avro_data and isinstance(avro_data[field], str):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(avro_data[field].replace('Z', '+00:00'))
                    avro_data[field] = int(dt.timestamp() * 1000)
                except Exception as e:
                    logger.warning(f"Could not convert timestamp field {field}: {e}")
        
        return avro_data


def load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON data from file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load JSON from {file_path}: {e}")
        return None


def find_schema_files(contracts_dir: Path, schema_name: str) -> Tuple[Optional[Path], Optional[Path]]:
    """Find Avro and JSON Schema files for a given schema name"""
    avro_path = None
    json_schema_path = None
    
    # Look for Avro schema
    avro_patterns = [
        f"{schema_name}.avsc",
        f"{schema_name}-v1.avsc"
    ]
    
    for pattern in avro_patterns:
        avro_candidate = contracts_dir / "schemas" / "avro" / pattern
        if avro_candidate.exists():
            avro_path = avro_candidate
            break
    
    # Look for JSON Schema
    json_patterns = [
        f"{schema_name}.json",
        f"{schema_name}-v1.json"
    ]
    
    for pattern in json_patterns:
        json_candidate = contracts_dir / "schemas" / "jsonschema" / pattern
        if json_candidate.exists():
            json_schema_path = json_candidate
            break
    
    return avro_path, json_schema_path


def validate_file(
    data_file: Path,
    avro_schema: Optional[Path] = None,
    json_schema: Optional[Path] = None,
    contracts_dir: Optional[Path] = None
) -> List[ValidationResult]:
    """
    Validate a JSON file against schemas
    
    Args:
        data_file: Path to JSON file to validate
        avro_schema: Path to Avro schema file
        json_schema: Path to JSON Schema file
        contracts_dir: Path to contracts directory for auto-discovery
    
    Returns:
        List of validation results
    """
    results = []
    
    # Load data
    data = load_json_file(data_file)
    if not data:
        result = ValidationResult(data_file, "Data Loading")
        result.add_error("Could not load JSON data")
        return [result]
    
    logger.info(f"Validating {data_file}")
    
    # Auto-discover schemas if not provided
    if not avro_schema and not json_schema and contracts_dir:
        # Try to determine schema name from data file
        schema_name = data_file.stem.split('-')[0]  # Extract base name
        avro_schema, json_schema = find_schema_files(contracts_dir, schema_name)
    
    # Validate against Avro schema
    if avro_schema and avro_schema.exists():
        validator = AvroSchemaValidator(avro_schema)
        result = validator.validate(data)
        results.append(result)
    elif avro_schema:
        result = ValidationResult(avro_schema, "Avro Schema")
        result.add_error("Schema file not found")
        results.append(result)
    
    # Validate against JSON Schema
    if json_schema and json_schema.exists():
        validator = JSONSchemaValidator(json_schema)
        result = validator.validate(data)
        results.append(result)
    elif json_schema:
        result = ValidationResult(json_schema, "JSON Schema")
        result.add_error("Schema file not found")
        results.append(result)
    
    if not results:
        result = ValidationResult(data_file, "Schema Discovery")
        result.add_error("No schemas found for validation")
        results.append(result)
    
    return results


def validate_directory(
    directory: Path,
    avro_schema: Optional[Path] = None,
    json_schema: Optional[Path] = None,
    contracts_dir: Optional[Path] = None,
    pattern: str = "*.json"
) -> List[ValidationResult]:
    """Validate all JSON files in a directory"""
    results = []
    
    json_files = list(directory.glob(pattern))
    if not json_files:
        logger.warning(f"No JSON files found in {directory}")
        return results
    
    logger.info(f"Found {len(json_files)} files to validate in {directory}")
    
    for json_file in sorted(json_files):
        file_results = validate_file(json_file, avro_schema, json_schema, contracts_dir)
        results.extend(file_results)
    
    return results


def print_summary(results: List[ValidationResult]):
    """Print validation summary"""
    total_files = len(set(r.file_path for r in results))
    total_validations = len(results)
    valid_validations = sum(1 for r in results if r.is_valid)
    
    print(f"\n📊 Validation Summary:")
    print(f"   Files processed: {total_files}")
    print(f"   Total validations: {total_validations}")
    print(f"   Successful: {valid_validations}")
    print(f"   Failed: {total_validations - valid_validations}")
    
    if valid_validations == total_validations:
        print("   ✅ All validations passed!")
    else:
        print("   ❌ Some validations failed")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Validate JSON data against Avro and JSON schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate single file against auto-discovered schemas
  python scripts/contracts/validate_event.py contracts/examples/article-ingest-v1/example-1-full-article.json
  
  # Validate with explicit schemas
  python scripts/contracts/validate_event.py data.json --avro-schema schema.avsc --json-schema schema.json
  
  # Validate all examples in directory
  python scripts/contracts/validate_event.py contracts/examples/article-ingest-v1/ --directory
  
  # Validate with custom contracts directory
  python scripts/contracts/validate_event.py data.json --contracts-dir /path/to/contracts
        """
    )
    
    parser.add_argument(
        "input",
        type=Path,
        help="JSON file or directory to validate"
    )
    
    parser.add_argument(
        "--avro-schema",
        type=Path,
        help="Path to Avro schema file (.avsc)"
    )
    
    parser.add_argument(
        "--json-schema",
        type=Path,
        help="Path to JSON Schema file (.json)"
    )
    
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=Path("contracts"),
        help="Path to contracts directory for auto-discovery (default: contracts/)"
    )
    
    parser.add_argument(
        "--directory", "-d",
        action="store_true",
        help="Validate all JSON files in directory"
    )
    
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="File pattern for directory validation (default: *.json)"
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
    
    # Validate input exists
    if not args.input.exists():
        logger.error(f"Input path not found: {args.input}")
        sys.exit(1)
    
    # Perform validation
    results = []
    
    if args.directory or args.input.is_dir():
        if not args.input.is_dir():
            logger.error(f"Directory flag specified but {args.input} is not a directory")
            sys.exit(1)
        
        results = validate_directory(
            directory=args.input,
            avro_schema=args.avro_schema,
            json_schema=args.json_schema,
            contracts_dir=args.contracts_dir,
            pattern=args.pattern
        )
    else:
        if not args.input.is_file():
            logger.error(f"File not found: {args.input}")
            sys.exit(1)
        
        results = validate_file(
            data_file=args.input,
            avro_schema=args.avro_schema,
            json_schema=args.json_schema,
            contracts_dir=args.contracts_dir
        )
    
    # Print results
    print("\n📋 Validation Results:")
    for result in results:
        print(f"\n{result}")
    
    # Print summary
    print_summary(results)
    
    # Exit with appropriate code
    all_valid = all(r.is_valid for r in results)
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
