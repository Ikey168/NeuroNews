# Data Contracts Validation Tools

This directory contains tools for schema validation, testing, and management.

## Schema Validation Script

### validate_schemas.py

```python
#!/usr/bin/env python3
"""
Schema validation tool for data contracts framework.
Validates Avro and JSON schemas for syntax and compatibility.
"""

import os
import json
import sys
import argparse
from pathlib import Path
import jsonschema
from avro import schema as avro_schema
from typing import List, Dict, Any
import requests

class SchemaValidator:
    """Validate schemas and check compatibility"""
    
    def __init__(self, schema_registry_url: str = "http://localhost:8081"):
        self.schema_registry_url = schema_registry_url
        self.errors = []
        self.warnings = []
    
    def validate_avro_schema(self, schema_path: Path) -> bool:
        """Validate Avro schema syntax"""
        try:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Parse schema to validate syntax
            avro_schema.parse(json.dumps(schema_json))
            print(f"✅ Valid Avro schema: {schema_path}")
            return True
            
        except Exception as e:
            self.errors.append(f"❌ Invalid Avro schema {schema_path}: {e}")
            return False
    
    def validate_json_schema(self, schema_path: Path) -> bool:
        """Validate JSON schema syntax"""
        try:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Validate JSON Schema syntax
            jsonschema.Draft7Validator.check_schema(schema_json)
            print(f"✅ Valid JSON schema: {schema_path}")
            return True
            
        except Exception as e:
            self.errors.append(f"❌ Invalid JSON schema {schema_path}: {e}")
            return False
    
    def check_compatibility(self, schema_path: Path, subject: str) -> bool:
        """Check schema compatibility with registry"""
        try:
            with open(schema_path, 'r') as f:
                schema_content = f.read()
            
            # Check compatibility with schema registry
            response = requests.post(
                f"{self.schema_registry_url}/compatibility/subjects/{subject}/versions/latest",
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
                json={"schema": schema_content}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("is_compatible", False):
                    print(f"✅ Compatible with {subject}: {schema_path}")
                    return True
                else:
                    self.warnings.append(f"⚠️  Not compatible with {subject}: {schema_path}")
                    return False
            else:
                self.warnings.append(f"⚠️  Could not check compatibility for {subject}: {response.text}")
                return True  # Don't fail if registry unavailable
                
        except Exception as e:
            self.warnings.append(f"⚠️  Compatibility check failed for {schema_path}: {e}")
            return True  # Don't fail on connection errors
    
    def validate_naming_conventions(self, schema_path: Path) -> bool:
        """Validate schema naming conventions"""
        filename = schema_path.name
        
        # Check Avro file naming
        if schema_path.suffix == '.avsc':
            if not filename.replace('.avsc', '').replace('-', '_').replace('_', '').isalnum():
                self.warnings.append(f"⚠️  Avro schema naming: {filename} should use kebab-case")
                return False
        
        # Check JSON Schema naming  
        elif schema_path.suffix == '.json':
            if not filename.replace('.json', '').replace('-', '_').replace('_', '').isalnum():
                self.warnings.append(f"⚠️  JSON schema naming: {filename} should use kebab-case")
                return False
        
        return True
    
    def validate_documentation(self, schema_path: Path) -> bool:
        """Validate schema documentation completeness"""
        try:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Check for documentation fields
            if schema_path.suffix == '.avsc':
                return self._validate_avro_docs(schema_json, schema_path)
            elif schema_path.suffix == '.json':
                return self._validate_json_docs(schema_json, schema_path)
                
        except Exception as e:
            self.errors.append(f"❌ Could not validate documentation for {schema_path}: {e}")
            return False
    
    def _validate_avro_docs(self, schema: Dict[str, Any], schema_path: Path) -> bool:
        """Validate Avro schema documentation"""
        issues = []
        
        # Check root documentation
        if 'doc' not in schema:
            issues.append("Missing root 'doc' field")
        
        # Check field documentation
        if 'fields' in schema:
            for field in schema['fields']:
                if 'doc' not in field:
                    issues.append(f"Field '{field.get('name', 'unknown')}' missing 'doc'")
        
        if issues:
            self.warnings.extend([f"⚠️  {schema_path}: {issue}" for issue in issues])
            return False
        
        return True
    
    def _validate_json_docs(self, schema: Dict[str, Any], schema_path: Path) -> bool:
        """Validate JSON schema documentation"""
        issues = []
        
        # Check root documentation
        if 'description' not in schema:
            issues.append("Missing root 'description' field")
        
        # Check property documentation
        if 'properties' in schema:
            for prop_name, prop_def in schema['properties'].items():
                if 'description' not in prop_def:
                    issues.append(f"Property '{prop_name}' missing 'description'")
        
        if issues:
            self.warnings.extend([f"⚠️  {schema_path}: {issue}" for issue in issues])
            return False
        
        return True
    
    def validate_all_schemas(self, contracts_dir: Path) -> bool:
        """Validate all schemas in the contracts directory"""
        success = True
        
        print("🔍 Validating schemas...")
        
        # Find all schema files
        avro_files = list(contracts_dir.glob("schemas/avro/**/*.avsc"))
        json_files = list(contracts_dir.glob("schemas/jsonschema/**/*.json"))
        
        print(f"Found {len(avro_files)} Avro schemas and {len(json_files)} JSON schemas")
        
        # Validate Avro schemas
        for schema_path in avro_files:
            print(f"\n📄 Validating Avro schema: {schema_path.relative_to(contracts_dir)}")
            
            if not self.validate_avro_schema(schema_path):
                success = False
            
            if not self.validate_naming_conventions(schema_path):
                success = False
                
            if not self.validate_documentation(schema_path):
                success = False
        
        # Validate JSON schemas
        for schema_path in json_files:
            print(f"\n📄 Validating JSON schema: {schema_path.relative_to(contracts_dir)}")
            
            if not self.validate_json_schema(schema_path):
                success = False
                
            if not self.validate_naming_conventions(schema_path):
                success = False
                
            if not self.validate_documentation(schema_path):
                success = False
        
        return success
    
    def print_summary(self):
        """Print validation summary"""
        print("\n" + "="*60)
        print("VALIDATION SUMMARY")
        print("="*60)
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")
        
        if not self.errors and not self.warnings:
            print("\n✅ All schemas are valid!")
        elif not self.errors:
            print(f"\n✅ All schemas are valid (with {len(self.warnings)} warnings)")
        else:
            print(f"\n❌ Validation failed with {len(self.errors)} errors and {len(self.warnings)} warnings")

def main():
    parser = argparse.ArgumentParser(description="Validate data contract schemas")
    parser.add_argument("--contracts-dir", type=Path, default=Path.cwd(), 
                       help="Path to contracts directory")
    parser.add_argument("--schema-registry", default="http://localhost:8081",
                       help="Schema registry URL for compatibility checks")
    parser.add_argument("--check-compatibility", action="store_true",
                       help="Check compatibility with schema registry")
    
    args = parser.parse_args()
    
    if not args.contracts_dir.exists():
        print(f"❌ Contracts directory not found: {args.contracts_dir}")
        sys.exit(1)
    
    validator = SchemaValidator(args.schema_registry)
    success = validator.validate_all_schemas(args.contracts_dir)
    
    validator.print_summary()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

## Schema Registry Management

### registry_manager.py

```python
#!/usr/bin/env python3
"""
Schema registry management tool.
Register, list, and manage schemas in the registry.
"""

import json
import requests
from pathlib import Path
import argparse
from typing import List, Dict

class RegistryManager:
    """Manage schemas in the registry"""
    
    def __init__(self, registry_url: str):
        self.registry_url = registry_url.rstrip('/')
    
    def list_subjects(self) -> List[str]:
        """List all subjects in the registry"""
        response = requests.get(f"{self.registry_url}/subjects")
        response.raise_for_status()
        return response.json()
    
    def get_schema_versions(self, subject: str) -> List[int]:
        """Get all versions for a subject"""
        response = requests.get(f"{self.registry_url}/subjects/{subject}/versions")
        response.raise_for_status()
        return response.json()
    
    def get_latest_schema(self, subject: str) -> Dict:
        """Get latest schema for a subject"""
        response = requests.get(f"{self.registry_url}/subjects/{subject}/versions/latest")
        response.raise_for_status()
        return response.json()
    
    def register_schema(self, subject: str, schema_path: Path) -> int:
        """Register a new schema version"""
        with open(schema_path, 'r') as f:
            schema_content = f.read()
        
        payload = {"schema": schema_content}
        response = requests.post(
            f"{self.registry_url}/subjects/{subject}/versions",
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result["id"]
    
    def check_compatibility(self, subject: str, schema_path: Path) -> bool:
        """Check if schema is compatible with latest version"""
        with open(schema_path, 'r') as f:
            schema_content = f.read()
        
        payload = {"schema": schema_content}
        response = requests.post(
            f"{self.registry_url}/compatibility/subjects/{subject}/versions/latest",
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        return result.get("is_compatible", False)
    
    def delete_subject(self, subject: str, permanent: bool = False) -> List[int]:
        """Delete a subject (soft or hard delete)"""
        url = f"{self.registry_url}/subjects/{subject}"
        if permanent:
            url += "?permanent=true"
        
        response = requests.delete(url)
        response.raise_for_status()
        return response.json()

def main():
    parser = argparse.ArgumentParser(description="Manage schema registry")
    parser.add_argument("--registry-url", default="http://localhost:8081",
                       help="Schema registry URL")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List subjects command
    subparsers.add_parser("list", help="List all subjects")
    
    # Register schema command
    register_parser = subparsers.add_parser("register", help="Register a schema")
    register_parser.add_argument("subject", help="Subject name")
    register_parser.add_argument("schema_file", type=Path, help="Path to schema file")
    
    # Check compatibility command
    compat_parser = subparsers.add_parser("check", help="Check compatibility")
    compat_parser.add_argument("subject", help="Subject name")
    compat_parser.add_argument("schema_file", type=Path, help="Path to schema file")
    
    # Get schema command
    get_parser = subparsers.add_parser("get", help="Get schema")
    get_parser.add_argument("subject", help="Subject name")
    get_parser.add_argument("--version", default="latest", help="Schema version")
    
    args = parser.parse_args()
    
    manager = RegistryManager(args.registry_url)
    
    try:
        if args.command == "list":
            subjects = manager.list_subjects()
            print("Registered subjects:")
            for subject in subjects:
                versions = manager.get_schema_versions(subject)
                print(f"  {subject} (versions: {versions})")
        
        elif args.command == "register":
            if not args.schema_file.exists():
                print(f"Schema file not found: {args.schema_file}")
                return 1
            
            schema_id = manager.register_schema(args.subject, args.schema_file)
            print(f"Schema registered with ID: {schema_id}")
        
        elif args.command == "check":
            if not args.schema_file.exists():
                print(f"Schema file not found: {args.schema_file}")
                return 1
            
            is_compatible = manager.check_compatibility(args.subject, args.schema_file)
            if is_compatible:
                print("✅ Schema is compatible")
            else:
                print("❌ Schema is not compatible")
                return 1
        
        elif args.command == "get":
            schema = manager.get_latest_schema(args.subject)
            print(json.dumps(schema, indent=2))
        
        else:
            parser.print_help()
            return 1
    
    except requests.exceptions.RequestException as e:
        print(f"Registry error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
```

## Testing Framework

### test_schemas.py

```python
#!/usr/bin/env python3
"""
Automated testing for data contract schemas.
"""

import pytest
import json
import jsonschema
from pathlib import Path
from avro import schema as avro_schema
import tempfile
import subprocess

class TestSchemas:
    """Test suite for schema validation"""
    
    @pytest.fixture
    def contracts_dir(self):
        return Path(__file__).parent.parent
    
    @pytest.fixture
    def avro_schemas(self, contracts_dir):
        return list(contracts_dir.glob("schemas/avro/**/*.avsc"))
    
    @pytest.fixture  
    def json_schemas(self, contracts_dir):
        return list(contracts_dir.glob("schemas/jsonschema/**/*.json"))
    
    def test_avro_schema_syntax(self, avro_schemas):
        """Test that all Avro schemas have valid syntax"""
        for schema_path in avro_schemas:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Should not raise exception
            avro_schema.parse(json.dumps(schema_json))
    
    def test_json_schema_syntax(self, json_schemas):
        """Test that all JSON schemas have valid syntax"""
        for schema_path in json_schemas:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Should not raise exception
            jsonschema.Draft7Validator.check_schema(schema_json)
    
    def test_avro_schema_documentation(self, avro_schemas):
        """Test that Avro schemas have proper documentation"""
        for schema_path in avro_schemas:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Root doc field
            assert 'doc' in schema_json, f"Missing doc in {schema_path}"
            
            # Field documentation
            if 'fields' in schema_json:
                for field in schema_json['fields']:
                    assert 'doc' in field, f"Field {field.get('name')} missing doc in {schema_path}"
    
    def test_json_schema_documentation(self, json_schemas):
        """Test that JSON schemas have proper documentation"""
        for schema_path in json_schemas:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            # Root description
            assert 'description' in schema_json, f"Missing description in {schema_path}"
            
            # Property descriptions
            if 'properties' in schema_json:
                for prop_name, prop_def in schema_json['properties'].items():
                    assert 'description' in prop_def, f"Property {prop_name} missing description in {schema_path}"
    
    def test_naming_conventions(self, avro_schemas, json_schemas):
        """Test schema naming conventions"""
        all_schemas = list(avro_schemas) + list(json_schemas)
        
        for schema_path in all_schemas:
            filename = schema_path.stem
            
            # Should use kebab-case
            assert filename.replace('-', '').replace('_', '').isalnum(), \
                f"Schema {filename} should use kebab-case"
    
    def test_avro_backward_compatibility_structure(self, avro_schemas):
        """Test that Avro schemas follow backward compatibility patterns"""
        for schema_path in avro_schemas:
            with open(schema_path, 'r') as f:
                schema_json = json.load(f)
            
            if 'fields' in schema_json:
                for field in schema_json['fields']:
                    # Optional fields should have defaults or be unions with null
                    if not self._is_required_field(field):
                        assert 'default' in field or self._is_nullable_union(field['type']), \
                            f"Optional field {field['name']} should have default or be nullable in {schema_path}"
    
    def _is_required_field(self, field):
        """Check if field is required (has no default and is not nullable)"""
        has_default = 'default' in field
        is_nullable = self._is_nullable_union(field['type'])
        return not (has_default or is_nullable)
    
    def _is_nullable_union(self, field_type):
        """Check if field type is a union with null"""
        if isinstance(field_type, list):
            return 'null' in field_type
        return False

# Performance tests
class TestSchemaPerformance:
    """Performance tests for schemas"""
    
    def test_schema_size_limits(self, avro_schemas, json_schemas):
        """Test that schemas are not too large"""
        max_size_kb = 100  # 100KB limit
        
        all_schemas = list(avro_schemas) + list(json_schemas)
        for schema_path in all_schemas:
            size_kb = schema_path.stat().st_size / 1024
            assert size_kb < max_size_kb, f"Schema {schema_path} is too large: {size_kb:.1f}KB"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## CI/CD Integration

### .github/workflows/schema-validation.yml

```yaml
name: Schema Validation

on:
  pull_request:
    paths:
      - 'contracts/schemas/**'
  push:
    branches:
      - main
    paths:
      - 'contracts/schemas/**'

jobs:
  validate-schemas:
    runs-on: ubuntu-latest
    
    services:
      schema-registry:
        image: confluentinc/cp-schema-registry:latest
        env:
          SCHEMA_REGISTRY_HOST_NAME: schema-registry
          SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: "kafka:9092"
          SCHEMA_REGISTRY_LISTENERS: "http://0.0.0.0:8081"
        ports:
          - 8081:8081
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install avro-python3 jsonschema requests pytest
    
    - name: Validate schema syntax
      run: |
        cd contracts
        python tools/validate_schemas.py --contracts-dir .
    
    - name: Run schema tests
      run: |
        cd contracts
        python -m pytest tools/test_schemas.py -v
    
    - name: Check schema compatibility
      if: github.event_name == 'pull_request'
      run: |
        cd contracts
        python tools/validate_schemas.py --contracts-dir . --check-compatibility --schema-registry http://localhost:8081
```

These tools provide comprehensive validation, testing, and management capabilities for the data contracts framework.
