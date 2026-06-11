#!/usr/bin/env python3
"""
Iceberg Table Contract Checker
Issue #372: Iceberg table contracts (warehouse layer)

This job validates that Iceberg tables in the warehouse layer conform to their
declared contracts including schema, partition specifications, and table properties.

Features:
- Schema validation (column names, types, constraints)
- Partition specification validation
- Table properties validation
- Contract enforcement in CI/CD pipeline
- Detailed reporting of contract violations

Usage:
    python jobs/iceberg_contract_check.py --table demo.marts.fact_articles
    python jobs/iceberg_contract_check.py --config dbt/models/marts/table_contracts.yml
    python jobs/iceberg_contract_check.py --all-tables
"""

import argparse
import json
import logging
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class PartitionSpec:
    """Represents an expected partition specification."""
    field: str
    transform: str
    type: str

@dataclass
class TableContract:
    """Represents a table contract definition."""
    name: str
    description: str
    columns: List[Dict[str, Any]]
    partition_spec: List[PartitionSpec]
    table_properties: Dict[str, str]
    table_format: str = "iceberg"

@dataclass
class ContractViolation:
    """Represents a contract violation."""
    table_name: str
    violation_type: str
    expected: Any
    actual: Any
    description: str

class IcebergContractChecker:
    """
    Validates Iceberg tables against declared contracts.
    """
    
    def __init__(self, spark_session: Optional[SparkSession] = None):
        """Initialize the contract checker."""
        self.spark = spark_session or self._create_spark_session()
        self.violations: List[ContractViolation] = []
        
    def _create_spark_session(self) -> SparkSession:
        """Create Spark session with Iceberg support."""
        return SparkSession.builder \
            .appName("IcebergContractChecker") \
            .config("spark.sql.catalog.demo", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.demo.catalog-impl", "org.apache.iceberg.rest.RESTCatalog") \
            .config("spark.sql.catalog.demo.uri", "http://localhost:8181") \
            .config("spark.sql.catalog.demo.warehouse", "s3a://demo-warehouse/") \
            .config("spark.sql.catalog.demo.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
            .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
            .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
            .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
            .config("spark.hadoop.fs.s3a.path.style.access", "true") \
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
            .getOrCreate()
    
    def load_contracts_from_file(self, contract_file: str) -> List[TableContract]:
        """Load table contracts from dbt YAML file."""
        try:
            with open(contract_file, 'r') as f:
                config = yaml.safe_load(f)
            
            contracts = []
            for model in config.get('models', []):
                # Extract partition spec
                partition_spec = []
                expected_partition_spec = model.get('config', {}).get('expected_partition_spec', [])
                for spec in expected_partition_spec:
                    partition_spec.append(PartitionSpec(
                        field=spec['field'],
                        transform=spec['transform'],
                        type=spec['type']
                    ))
                
                # Extract table properties
                table_properties = model.get('config', {}).get('expected_table_properties', {})
                
                contract = TableContract(
                    name=model['name'],
                    description=model.get('description', ''),
                    columns=model.get('columns', []),
                    partition_spec=partition_spec,
                    table_properties=table_properties,
                    table_format=model.get('config', {}).get('table_format', 'iceberg')
                )
                contracts.append(contract)
                
            logger.info(f"Loaded {len(contracts)} table contracts from {contract_file}")
            return contracts
            
        except Exception as e:
            logger.error(f"Failed to load contracts from {contract_file}: {e}")
            raise
    
    def get_table_schema(self, table_name: str) -> StructType:
        """Get the actual schema of an Iceberg table."""
        try:
            # Use DESCRIBE TABLE EXTENDED to get detailed schema info
            describe_df = self.spark.sql(f"DESCRIBE TABLE EXTENDED {table_name}")
            describe_rows = describe_df.collect()
            
            # Also get the actual table for schema
            table_df = self.spark.table(table_name)
            return table_df.schema
            
        except Exception as e:
            logger.error(f"Failed to get schema for table {table_name}: {e}")
            raise
    
    def get_table_partition_spec(self, table_name: str) -> List[Dict[str, Any]]:
        """Get the actual partition specification of an Iceberg table."""
        try:
            # Query the partitions metadata table
            partitions_df = self.spark.sql(f"SELECT * FROM {table_name}.partitions LIMIT 1")
            
            # Get partition columns from DESCRIBE TABLE
            describe_df = self.spark.sql(f"DESCRIBE TABLE EXTENDED {table_name}")
            describe_rows = describe_df.collect()
            
            partition_info = []
            in_partition_section = False
            
            for row in describe_rows:
                col_name = row['col_name']
                data_type = row['data_type']
                comment = row['comment']
                
                if col_name == '# Partition Information':
                    in_partition_section = True
                    continue
                elif col_name.startswith('#') or col_name == '':
                    in_partition_section = False
                    continue
                    
                if in_partition_section and col_name and data_type:
                    partition_info.append({
                        'field': col_name,
                        'type': data_type,
                        'transform': 'identity'  # Default for most cases
                    })
            
            return partition_info
            
        except Exception as e:
            logger.warning(f"Could not get partition spec for {table_name}: {e}")
            return []
    
    def get_table_properties(self, table_name: str) -> Dict[str, str]:
        """Get the actual table properties of an Iceberg table."""
        try:
            # Use SHOW TBLPROPERTIES to get table properties
            properties_df = self.spark.sql(f"SHOW TBLPROPERTIES {table_name}")
            properties_rows = properties_df.collect()
            
            properties = {}
            for row in properties_rows:
                key = row['key']
                value = row['value']
                properties[key] = value
            
            return properties
            
        except Exception as e:
            logger.warning(f"Could not get table properties for {table_name}: {e}")
            return {}
    
    def validate_schema(self, table_name: str, contract: TableContract) -> List[ContractViolation]:
        """Validate table schema against contract."""
        violations = []
        
        try:
            actual_schema = self.get_table_schema(table_name)
            actual_fields = {field.name: field for field in actual_schema.fields}
            
            # Check that all required columns exist with correct types
            for column in contract.columns:
                col_name = column['name']
                expected_type = column['data_type']
                
                if col_name not in actual_fields:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="missing_column",
                        expected=col_name,
                        actual="missing",
                        description=f"Required column '{col_name}' is missing from table"
                    ))
                    continue
                
                actual_field = actual_fields[col_name]
                actual_type = str(actual_field.dataType).lower()
                
                # Normalize type names for comparison
                expected_type_normalized = self._normalize_type_name(expected_type)
                actual_type_normalized = self._normalize_type_name(actual_type)
                
                if expected_type_normalized != actual_type_normalized:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="type_mismatch",
                        expected=expected_type,
                        actual=str(actual_field.dataType),
                        description=f"Column '{col_name}' type mismatch: expected {expected_type}, got {actual_field.dataType}"
                    ))
                
                # Check constraints (nullable)
                constraints = column.get('constraints', [])
                for constraint in constraints:
                    if constraint.get('type') == 'not_null':
                        if actual_field.nullable:
                            violations.append(ContractViolation(
                                table_name=table_name,
                                violation_type="nullable_violation",
                                expected="not_null",
                                actual="nullable",
                                description=f"Column '{col_name}' should be NOT NULL but is nullable"
                            ))
            
        except Exception as e:
            violations.append(ContractViolation(
                table_name=table_name,
                violation_type="schema_validation_error",
                expected="valid_schema",
                actual="error",
                description=f"Failed to validate schema: {e}"
            ))
        
        return violations
    
    def validate_partition_spec(self, table_name: str, contract: TableContract) -> List[ContractViolation]:
        """Validate partition specification against contract."""
        violations = []
        
        try:
            actual_partitions = self.get_table_partition_spec(table_name)
            expected_partitions = contract.partition_spec
            
            # Convert to dictionaries for easier comparison
            actual_partition_fields = {p['field']: p for p in actual_partitions}
            expected_partition_fields = {p.field: p for p in expected_partitions}
            
            # Check that all expected partitions exist
            for expected_field, expected_spec in expected_partition_fields.items():
                if expected_field not in actual_partition_fields:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="missing_partition",
                        expected=f"{expected_field} ({expected_spec.type})",
                        actual="missing",
                        description=f"Expected partition field '{expected_field}' is missing"
                    ))
                    continue
                
                actual_spec = actual_partition_fields[expected_field]
                
                # Validate partition type (normalize type names)
                expected_type_normalized = self._normalize_type_name(expected_spec.type)
                actual_type_normalized = self._normalize_type_name(actual_spec['type'])
                
                if expected_type_normalized != actual_type_normalized:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="partition_type_mismatch",
                        expected=f"{expected_field}:{expected_spec.type}",
                        actual=f"{expected_field}:{actual_spec['type']}",
                        description=f"Partition field '{expected_field}' type mismatch: expected {expected_spec.type}, got {actual_spec['type']}"
                    ))
            
            # Check for unexpected partitions
            for actual_field in actual_partition_fields:
                if actual_field not in expected_partition_fields:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="unexpected_partition",
                        expected="not_present",
                        actual=actual_field,
                        description=f"Unexpected partition field '{actual_field}' found in table"
                    ))
        
        except Exception as e:
            violations.append(ContractViolation(
                table_name=table_name,
                violation_type="partition_validation_error",
                expected="valid_partitions",
                actual="error",
                description=f"Failed to validate partitions: {e}"
            ))
        
        return violations
    
    def validate_table_properties(self, table_name: str, contract: TableContract) -> List[ContractViolation]:
        """Validate table properties against contract."""
        violations = []
        
        try:
            actual_properties = self.get_table_properties(table_name)
            expected_properties = contract.table_properties
            
            for expected_key, expected_value in expected_properties.items():
                if expected_key not in actual_properties:
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="missing_property",
                        expected=f"{expected_key}={expected_value}",
                        actual="missing",
                        description=f"Required table property '{expected_key}' is missing"
                    ))
                    continue
                
                actual_value = actual_properties[expected_key]
                if str(expected_value) != str(actual_value):
                    violations.append(ContractViolation(
                        table_name=table_name,
                        violation_type="property_value_mismatch",
                        expected=f"{expected_key}={expected_value}",
                        actual=f"{expected_key}={actual_value}",
                        description=f"Table property '{expected_key}' value mismatch: expected '{expected_value}', got '{actual_value}'"
                    ))
            
            # Special validation for critical Iceberg properties
            critical_properties = ['write.format.default', 'delete.mode']
            for prop in critical_properties:
                if prop in expected_properties:
                    logger.info(f"Validating critical Iceberg property: {prop}")
        
        except Exception as e:
            violations.append(ContractViolation(
                table_name=table_name,
                violation_type="property_validation_error",
                expected="valid_properties",
                actual="error",
                description=f"Failed to validate table properties: {e}"
            ))
        
        return violations
    
    def _normalize_type_name(self, type_name: str) -> str:
        """Normalize data type names for comparison."""
        type_name = str(type_name).lower().strip()
        
        # Handle common type variations
        type_mappings = {
            'string': 'string',
            'varchar': 'string',
            'text': 'string',
            'int': 'int',
            'integer': 'int',
            'bigint': 'bigint',
            'long': 'bigint',
            'double': 'double',
            'float': 'float',
            'decimal': 'decimal',
            'boolean': 'boolean',
            'bool': 'boolean',
            'timestamp': 'timestamp',
            'timestamptype': 'timestamp',
            'date': 'date',
            'datetype': 'date'
        }
        
        # Remove parentheses and extra whitespace
        type_name = type_name.split('(')[0].strip()
        
        return type_mappings.get(type_name, type_name)
    
    def validate_table_contract(self, table_name: str, contract: TableContract) -> List[ContractViolation]:
        """Validate a single table against its contract."""
        logger.info(f"Validating contract for table: {table_name}")
        
        all_violations = []
        
        # Validate schema
        schema_violations = self.validate_schema(table_name, contract)
        all_violations.extend(schema_violations)
        
        # Validate partition specification
        partition_violations = self.validate_partition_spec(table_name, contract)
        all_violations.extend(partition_violations)
        
        # Validate table properties
        property_violations = self.validate_table_properties(table_name, contract)
        all_violations.extend(property_violations)
        
        if all_violations:
            logger.warning(f"Found {len(all_violations)} contract violations for table {table_name}")
        else:
            logger.info(f"Table {table_name} passes all contract validations")
        
        return all_violations
    
    def check_contracts(self, contracts: List[TableContract], table_prefix: str = "demo.marts") -> bool:
        """Check multiple table contracts."""
        all_violations = []
        
        for contract in contracts:
            full_table_name = f"{table_prefix}.{contract.name}"
            
            try:
                violations = self.validate_table_contract(full_table_name, contract)
                all_violations.extend(violations)
            except Exception as e:
                logger.error(f"Failed to validate contract for {full_table_name}: {e}")
                all_violations.append(ContractViolation(
                    table_name=full_table_name,
                    violation_type="validation_error",
                    expected="successful_validation",
                    actual="error",
                    description=f"Contract validation failed with error: {e}"
                ))
        
        # Store violations for reporting
        self.violations = all_violations
        
        # Report results
        self.print_violation_report()
        
        return len(all_violations) == 0
    
    def print_violation_report(self):
        """Print a detailed report of contract violations."""
        if not self.violations:
            print("🎉 All table contracts are valid!")
            return
        
        print(f"\n❌ Found {len(self.violations)} contract violations:\n")
        
        # Group violations by table
        violations_by_table = {}
        for violation in self.violations:
            if violation.table_name not in violations_by_table:
                violations_by_table[violation.table_name] = []
            violations_by_table[violation.table_name].append(violation)
        
        for table_name, table_violations in violations_by_table.items():
            print(f"📋 Table: {table_name}")
            print(f"   Violations: {len(table_violations)}")
            
            for violation in table_violations:
                print(f"   ❌ {violation.violation_type.replace('_', ' ').title()}")
                print(f"      Expected: {violation.expected}")
                print(f"      Actual: {violation.actual}")
                print(f"      Description: {violation.description}")
                print()
    
    def export_violation_report(self, output_file: str):
        """Export violation report to JSON file."""
        report = {
            "timestamp": str(datetime.now()),
            "total_violations": len(self.violations),
            "violations": [
                {
                    "table_name": v.table_name,
                    "violation_type": v.violation_type,
                    "expected": str(v.expected),
                    "actual": str(v.actual),
                    "description": v.description
                }
                for v in self.violations
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Violation report exported to {output_file}")

def main():
    """Main function for CLI usage."""
    parser = argparse.ArgumentParser(description="Iceberg Table Contract Checker")
    parser.add_argument("--table", help="Specific table to check (e.g., demo.marts.fact_articles)")
    parser.add_argument("--config", default="dbt/models/marts/table_contracts.yml", 
                       help="Path to table contracts YAML file")
    parser.add_argument("--all-tables", action="store_true", 
                       help="Check all tables defined in the config file")
    parser.add_argument("--table-prefix", default="demo.marts",
                       help="Table prefix for fully qualified names")
    parser.add_argument("--output", help="Output file for violation report (JSON)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize checker
        checker = IcebergContractChecker()
        
        # Load contracts
        contracts = checker.load_contracts_from_file(args.config)
        
        if args.table:
            # Check specific table
            table_name = args.table
            contract_name = table_name.split('.')[-1]  # Get table name from full path
            
            # Find matching contract
            matching_contract = None
            for contract in contracts:
                if contract.name == contract_name:
                    matching_contract = contract
                    break
            
            if not matching_contract:
                logger.error(f"No contract found for table {contract_name}")
                return 1
            
            violations = checker.validate_table_contract(table_name, matching_contract)
            checker.violations = violations
            
        elif args.all_tables:
            # Check all tables
            success = checker.check_contracts(contracts, args.table_prefix)
            
        else:
            logger.error("Must specify either --table or --all-tables")
            return 1
        
        # Export report if requested
        if args.output:
            checker.export_violation_report(args.output)
        
        # Print final summary
        if checker.violations:
            checker.print_violation_report()
            return 1
        else:
            print("✅ All table contracts validated successfully!")
            return 0
            
    except Exception as e:
        logger.error(f"Contract check failed: {e}")
        if args.verbose:
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
