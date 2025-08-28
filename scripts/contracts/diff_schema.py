#!/usr/bin/env python3
"""
Schema Breaking Change Detector for CI/CD Pipeline

This script compares changed schema files against their latest published versions
to detect breaking changes according to BACKWARD_TRANSITIVE compatibility rules.

Usage:
    python diff_schema.py --base-ref origin/main --head-ref HEAD
    python diff_schema.py --file contracts/schemas/avro/article-ingest-v1.avsc

Schema Compatibility Rules (BACKWARD_TRANSITIVE):
- ✅ ALLOWED: Adding optional fields (with defaults)
- ✅ ALLOWED: Adding new enum values
- ✅ ALLOWED: Widening numeric types (int -> long, float -> double)
- ✅ ALLOWED: Documentation changes
- ❌ FORBIDDEN: Removing required fields
- ❌ FORBIDDEN: Changing field types (incompatible changes)
- ❌ FORBIDDEN: Making optional fields required
- ❌ FORBIDDEN: Removing enum values
- ❌ FORBIDDEN: Changing field names
"""

import json
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SchemaCompatibilityError(Exception):
    """Exception raised when schema compatibility is violated."""
    pass


class SchemaBreakingChangeDetector:
    """Detects breaking changes in Avro and JSON schemas."""
    
    def __init__(self):
        self.breaking_changes = []
        self.warnings = []
        
    def detect_changes(self, base_ref: str = "origin/main", head_ref: str = "HEAD") -> bool:
        """
        Detect breaking changes between two git references.
        
        Returns:
            True if breaking changes found, False otherwise
        """
        changed_files = self._get_changed_schema_files(base_ref, head_ref)
        
        if not changed_files:
            logger.info("No schema files changed")
            return False
            
        logger.info(f"Found {len(changed_files)} changed schema files")
        
        has_breaking_changes = False
        
        for file_path in changed_files:
            try:
                if self._analyze_schema_file(file_path, base_ref):
                    has_breaking_changes = True
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")
                has_breaking_changes = True
                
        return has_breaking_changes
    
    def _get_changed_schema_files(self, base_ref: str, head_ref: str) -> List[str]:
        """Get list of changed schema files between two references."""
        try:
            # Get changed files
            result = subprocess.run([
                'git', 'diff', '--name-only', f'{base_ref}...{head_ref}'
            ], capture_output=True, text=True, check=True)
            
            changed_files = result.stdout.strip().split('\n')
            
            # Filter for schema files
            schema_files = []
            for file_path in changed_files:
                if file_path and self._is_schema_file(file_path):
                    schema_files.append(file_path)
                    
            return schema_files
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get changed files: {e}")
            return []
    
    def _is_schema_file(self, file_path: str) -> bool:
        """Check if file is a schema file."""
        return (
            file_path.startswith('contracts/schemas/') and 
            (file_path.endswith('.avsc') or file_path.endswith('.json'))
        )
    
    def _analyze_schema_file(self, file_path: str, base_ref: str) -> bool:
        """
        Analyze a single schema file for breaking changes.
        
        Returns:
            True if breaking changes found, False otherwise
        """
        logger.info(f"Analyzing schema file: {file_path}")
        
        # Get old and new versions
        old_schema = self._get_file_content_at_ref(file_path, base_ref)
        
        # For current working directory comparison
        try:
            with open(file_path, 'r') as f:
                new_schema = f.read()
        except FileNotFoundError:
            new_schema = None
        
        if old_schema is None:
            logger.info(f"New schema file: {file_path}")
            return False  # New files are not breaking changes
            
        if new_schema is None:
            logger.error(f"Schema file deleted: {file_path}")
            self.breaking_changes.append(f"🚨 BREAKING: Schema file deleted: {file_path}")
            return True
        
        # Check if files are identical
        if old_schema.strip() == new_schema.strip():
            logger.info(f"No changes in schema file: {file_path}")
            return False
        
        # Parse schemas
        try:
            old_parsed = json.loads(old_schema)
            new_parsed = json.loads(new_schema)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse schema {file_path}: {e}")
            self.breaking_changes.append(f"🚨 BREAKING: Invalid JSON in {file_path}: {e}")
            return True
        
        # Detect breaking changes based on schema type
        if file_path.endswith('.avsc'):
            return self._analyze_avro_schema(file_path, old_parsed, new_parsed)
        else:
            return self._analyze_json_schema(file_path, old_parsed, new_parsed)
    
    def _get_file_content_at_ref(self, file_path: str, ref: str) -> Optional[str]:
        """Get file content at a specific git reference."""
        try:
            result = subprocess.run([
                'git', 'show', f'{ref}:{file_path}'
            ], capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError:
            return None  # File doesn't exist at this ref
    
    def _analyze_avro_schema(self, file_path: str, old_schema: Dict, new_schema: Dict) -> bool:
        """Analyze Avro schema for breaking changes."""
        logger.info(f"Analyzing Avro schema: {file_path}")
        
        has_breaking_changes = False
        
        # Check if it's a record schema
        if old_schema.get('type') == 'record' and new_schema.get('type') == 'record':
            has_breaking_changes |= self._check_avro_record_compatibility(
                file_path, old_schema, new_schema
            )
        elif old_schema.get('type') != new_schema.get('type'):
            self.breaking_changes.append(
                f"🚨 BREAKING: Type changed in {file_path}: "
                f"{old_schema.get('type')} -> {new_schema.get('type')}"
            )
            has_breaking_changes = True
        
        return has_breaking_changes
    
    def _check_avro_record_compatibility(self, file_path: str, old_schema: Dict, new_schema: Dict) -> bool:
        """Check Avro record compatibility."""
        has_breaking_changes = False
        
        old_fields = {f['name']: f for f in old_schema.get('fields', [])}
        new_fields = {f['name']: f for f in new_schema.get('fields', [])}
        
        # Check for removed fields
        removed_fields = set(old_fields.keys()) - set(new_fields.keys())
        for field_name in removed_fields:
            old_field = old_fields[field_name]
            if not self._has_default_value(old_field):
                self.breaking_changes.append(
                    f"🚨 BREAKING: Required field removed in {file_path}: {field_name}"
                )
                has_breaking_changes = True
            else:
                self.warnings.append(
                    f"⚠️  WARNING: Optional field removed in {file_path}: {field_name}"
                )
        
        # Check for field type changes
        common_fields = set(old_fields.keys()) & set(new_fields.keys())
        for field_name in common_fields:
            old_field = old_fields[field_name]
            new_field = new_fields[field_name]
            
            if not self._are_avro_types_compatible(old_field['type'], new_field['type']):
                self.breaking_changes.append(
                    f"🚨 BREAKING: Incompatible type change in {file_path}.{field_name}: "
                    f"{old_field['type']} -> {new_field['type']}"
                )
                has_breaking_changes = True
        
        # Check for new required fields
        new_required_fields = set(new_fields.keys()) - set(old_fields.keys())
        for field_name in new_required_fields:
            new_field = new_fields[field_name]
            if not self._has_default_value(new_field):
                self.breaking_changes.append(
                    f"🚨 BREAKING: New required field added in {file_path}: {field_name}"
                )
                has_breaking_changes = True
        
        return has_breaking_changes
    
    def _has_default_value(self, field: Dict) -> bool:
        """Check if an Avro field has a default value."""
        return 'default' in field or self._is_nullable_type(field.get('type'))
    
    def _is_nullable_type(self, field_type: Any) -> bool:
        """Check if an Avro type is nullable (union with null)."""
        if isinstance(field_type, list):
            return 'null' in field_type
        return False
    
    def _are_avro_types_compatible(self, old_type: Any, new_type: Any) -> bool:
        """Check if Avro types are backward compatible."""
        # Exact match
        if old_type == new_type:
            return True
        
        # Handle union types
        if isinstance(old_type, list) and isinstance(new_type, list):
            # New union should contain all old types
            return set(old_type).issubset(set(new_type))
        
        # Handle primitive type widening
        if isinstance(old_type, str) and isinstance(new_type, str):
            compatible_widenings = {
                'int': ['long'],
                'float': ['double'],
            }
            return new_type in compatible_widenings.get(old_type, [])
        
        return False
    
    def _analyze_json_schema(self, file_path: str, old_schema: Dict, new_schema: Dict) -> bool:
        """Analyze JSON schema for breaking changes."""
        logger.info(f"Analyzing JSON schema: {file_path}")
        
        has_breaking_changes = False
        
        # Check required fields
        old_required = set(old_schema.get('required', []))
        new_required = set(new_schema.get('required', []))
        
        # New required fields are breaking
        added_required = new_required - old_required
        if added_required:
            self.breaking_changes.append(
                f"🚨 BREAKING: New required fields in {file_path}: {list(added_required)}"
            )
            has_breaking_changes = True
        
        # Check property changes
        old_properties = old_schema.get('properties', {})
        new_properties = new_schema.get('properties', {})
        
        # Removed properties that were required
        removed_properties = set(old_properties.keys()) - set(new_properties.keys())
        removed_required = removed_properties & old_required
        if removed_required:
            self.breaking_changes.append(
                f"🚨 BREAKING: Required properties removed in {file_path}: {list(removed_required)}"
            )
            has_breaking_changes = True
        
        # Check property type changes
        common_properties = set(old_properties.keys()) & set(new_properties.keys())
        for prop_name in common_properties:
            old_prop = old_properties[prop_name]
            new_prop = new_properties[prop_name]
            
            old_type = old_prop.get('type')
            new_type = new_prop.get('type')
            
            if old_type != new_type and not self._are_json_types_compatible(old_type, new_type):
                self.breaking_changes.append(
                    f"🚨 BREAKING: Incompatible type change in {file_path}.{prop_name}: "
                    f"{old_type} -> {new_type}"
                )
                has_breaking_changes = True
        
        return has_breaking_changes
    
    def _are_json_types_compatible(self, old_type: Any, new_type: Any) -> bool:
        """Check if JSON schema types are compatible."""
        if old_type == new_type:
            return True
        
        # Handle array types
        if isinstance(old_type, list) and isinstance(new_type, list):
            return set(old_type).issubset(set(new_type))
        
        # Handle type widening
        if isinstance(old_type, str) and isinstance(new_type, str):
            compatible_widenings = {
                'integer': ['number'],
            }
            return new_type in compatible_widenings.get(old_type, [])
        
        return False
    
    def report_results(self) -> bool:
        """Report analysis results and return whether breaking changes were found."""
        if self.breaking_changes:
            print("\n🚨 SCHEMA BREAKING CHANGES DETECTED:")
            print("=" * 50)
            for change in self.breaking_changes:
                print(change)
            print("\n💡 To fix these issues:")
            print("- Add default values to new required fields")
            print("- Use field aliases instead of renaming")
            print("- Only add optional fields or widen types")
            print("- Follow BACKWARD_TRANSITIVE compatibility rules")
            return True
        
        if self.warnings:
            print("\n⚠️  SCHEMA WARNINGS:")
            print("=" * 30)
            for warning in self.warnings:
                print(warning)
        
        if not self.breaking_changes and not self.warnings:
            print("\n✅ No breaking schema changes detected!")
        
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect breaking changes in schema files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--base-ref',
        default='origin/main',
        help='Base git reference to compare against (default: origin/main)'
    )
    parser.add_argument(
        '--head-ref',
        default='HEAD',
        help='Head git reference to compare (default: HEAD)'
    )
    parser.add_argument(
        '--file',
        help='Analyze a specific schema file instead of git diff'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    detector = SchemaBreakingChangeDetector()
    
    try:
        if args.file:
            # Analyze single file
            has_breaking_changes = detector._analyze_schema_file(args.file, args.base_ref)
        else:
            # Analyze all changed files
            has_breaking_changes = detector.detect_changes(args.base_ref, args.head_ref)
        
        # Report results
        has_breaking_changes = detector.report_results()
        
        # Exit with appropriate code
        sys.exit(1 if has_breaking_changes else 0)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
