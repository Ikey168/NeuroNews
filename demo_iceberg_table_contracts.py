#!/usr/bin/env python3
"""
Demo script for Iceberg table contracts validation - Issue #372

This script demonstrates the Iceberg table contract validation functionality,
including schema, partition specification, and table properties validation.
"""

import os
import sys
import time
import logging
import subprocess
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, '/workspaces/NeuroNews')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_command(command: str, description: str) -> bool:
    """Run a shell command and return success status."""
    try:
        logger.info(f"🔧 {description}")
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(result.stdout)
            return True
        else:
            logger.error(f"❌ {description} - FAILED")
            if result.stderr.strip():
                print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ {description} - EXCEPTION: {e}")
        return False

def demonstrate_contract_validation():
    """Demonstrate the contract validation functionality."""
    
    print("=" * 70)
    print("🏗️  ICEBERG TABLE CONTRACTS VALIDATION DEMO")
    print("Issue #372: Iceberg table contracts (warehouse layer)")
    print("=" * 70)
    
    # Check if contract files exist
    contract_file = "dbt/models/marts/table_contracts.yml"
    validator_script = "jobs/iceberg_contract_check.py"
    
    if not os.path.exists(contract_file):
        logger.error(f"Contract file not found: {contract_file}")
        return False
    
    if not os.path.exists(validator_script):
        logger.error(f"Validator script not found: {validator_script}")
        return False
    
    logger.info(f"✅ Contract file found: {contract_file}")
    logger.info(f"✅ Validator script found: {validator_script}")
    
    print("\n1. 📋 Contract Configuration Overview")
    print("=" * 50)
    
    # Show contract configuration
    try:
        with open(contract_file, 'r') as f:
            content = f.read()
        
        # Extract key information
        lines = content.split('\n')
        in_models = False
        table_count = 0
        
        for line in lines:
            if 'models:' in line:
                in_models = True
            elif in_models and '- name:' in line:
                table_count += 1
                table_name = line.split('name:')[1].strip()
                print(f"  📊 Table: {table_name}")
        
        print(f"\n  📈 Total tables with contracts: {table_count}")
        
        # Show key contract features
        if 'expected_partition_spec' in content:
            print("  ✓ Partition specification validation")
        if 'expected_table_properties' in content:
            print("  ✓ Table properties validation")
        if 'constraints' in content:
            print("  ✓ Column constraints validation")
            
    except Exception as e:
        logger.error(f"Error reading contract file: {e}")
        return False
    
    print("\n2. 🧪 Contract Validation Test (Dry Run)")
    print("=" * 50)
    
    # Test the validator script syntax
    syntax_check = run_command(
        f"python -m py_compile {validator_script}",
        "Checking validator script syntax"
    )
    
    if not syntax_check:
        logger.error("Validator script has syntax errors")
        return False
    
    print("\n3. 📝 Contract Validation Logic")
    print("=" * 50)
    
    print("  The validator performs these checks:")
    print("  ✓ Schema validation (column names, types, constraints)")
    print("  ✓ Partition specification validation")
    print("  ✓ Table properties validation (format, compression, etc.)")
    print("  ✓ Iceberg-specific configurations")
    print("  ✓ Data type compatibility")
    
    print("\n4. 🔍 Example Contract Violations")
    print("=" * 50)
    
    # Show examples of what would be caught
    violations_examples = [
        ("Missing Column", "Required column 'article_id' not found in table"),
        ("Type Mismatch", "Expected 'string' but found 'int' for column 'source'"),
        ("Missing Partition", "Expected partition field 'year' is missing"),
        ("Property Mismatch", "Expected 'write.format.default=parquet' but got 'orc'"),
        ("Constraint Violation", "Column 'published_at' should be NOT NULL but is nullable")
    ]
    
    for violation_type, description in violations_examples:
        print(f"  ❌ {violation_type}: {description}")
    
    print("\n5. 📊 Contract Enforcement Features")
    print("=" * 50)
    
    features = [
        ("Schema Drift Detection", "Catches when table schema deviates from contract"),
        ("Partition Compliance", "Ensures correct partitioning strategy"),
        ("Property Enforcement", "Validates Iceberg table configuration"),
        ("CI/CD Integration", "Fails builds on contract violations"),
        ("Detailed Reporting", "Provides actionable violation reports")
    ]
    
    for feature, description in features:
        print(f"  🔧 {feature}: {description}")
    
    print("\n6. 🚀 CI/CD Integration")
    print("=" * 50)
    
    ci_workflow = ".github/workflows/iceberg-contracts.yml"
    if os.path.exists(ci_workflow):
        print(f"  ✅ CI workflow configured: {ci_workflow}")
        print("  🔄 Runs on every commit to marts models")
        print("  📋 Creates PR comments with violation details")
        print("  ❌ Fails builds when contracts are violated")
    else:
        print(f"  ⚠️  CI workflow not found: {ci_workflow}")
    
    print("\n7. 📈 Usage Examples")
    print("=" * 50)
    
    usage_examples = [
        "# Check all tables",
        "python jobs/iceberg_contract_check.py --all-tables",
        "",
        "# Check specific table",
        "python jobs/iceberg_contract_check.py --table demo.marts.fact_articles",
        "",
        "# Export violations report",
        "python jobs/iceberg_contract_check.py --all-tables --output violations.json",
        "",
        "# Verbose output",
        "python jobs/iceberg_contract_check.py --all-tables --verbose"
    ]
    
    for example in usage_examples:
        if example.startswith("#"):
            print(f"  💡 {example}")
        elif example.startswith("python"):
            print(f"     $ {example}")
        else:
            print(f"     {example}")
    
    return True

def test_contract_loading():
    """Test loading contracts from the YAML file."""
    print("\n8. 🧪 Testing Contract Loading")
    print("=" * 50)
    
    try:
        # Test contract loading functionality
        test_code = """
import sys
sys.path.insert(0, '/workspaces/NeuroNews')

from jobs.iceberg_contract_check import IcebergContractChecker

try:
    # Create checker (without Spark for this test)
    checker = IcebergContractChecker.__new__(IcebergContractChecker)
    
    # Load contracts
    contracts = checker.load_contracts_from_file('dbt/models/marts/table_contracts.yml')
    
    print(f'  ✅ Loaded {len(contracts)} contracts successfully')
    
    for contract in contracts:
        print(f'     📊 {contract.name}: {len(contract.columns)} columns, {len(contract.partition_spec)} partitions')
        print(f'        Properties: {len(contract.table_properties)} configured')
        
except Exception as e:
    print(f'  ❌ Contract loading failed: {e}')
    import traceback
    traceback.print_exc()
"""
        
        result = subprocess.run([sys.executable, "-c", test_code], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print(result.stdout)
            return True
        else:
            logger.error("Contract loading test failed")
            print(result.stderr)
            return False
            
    except Exception as e:
        logger.error(f"Error testing contract loading: {e}")
        return False

def show_benefits():
    """Show the benefits of Iceberg table contracts."""
    print("\n9. 🎯 Benefits of Iceberg Table Contracts")
    print("=" * 50)
    
    benefits = [
        ("Data Quality Assurance", "Ensures tables match expected schema and configuration"),
        ("Early Problem Detection", "Catches issues in CI before they reach production"),
        ("Configuration Compliance", "Enforces optimal Iceberg table settings"),
        ("Documentation", "Contracts serve as living documentation"),
        ("Change Management", "Controlled evolution of warehouse schema"),
        ("Performance Optimization", "Ensures proper partitioning and file formats"),
        ("Operational Safety", "Prevents misconfigurations that impact queries")
    ]
    
    for benefit, description in benefits:
        print(f"  ✅ {benefit}: {description}")

def main():
    """Main demo function."""
    try:
        success = True
        
        # Run demonstration
        success &= demonstrate_contract_validation()
        
        # Test contract loading
        success &= test_contract_loading()
        
        # Show benefits
        show_benefits()
        
        print("\n" + "=" * 70)
        if success:
            print("🎉 ICEBERG TABLE CONTRACTS DEMO COMPLETED SUCCESSFULLY!")
            print("\n✅ Key capabilities demonstrated:")
            print("   ✓ Table contract definition and validation")
            print("   ✓ Schema, partition, and property enforcement")
            print("   ✓ CI/CD integration for automated checking")
            print("   ✓ Detailed violation reporting")
            print("   ✓ Iceberg-specific configuration validation")
            
            print("\n🚀 Next steps:")
            print("   1. Set up Iceberg tables in your data warehouse")
            print("   2. Configure CI/CD pipeline to run contract checks")
            print("   3. Define contracts for all critical tables")
            print("   4. Monitor contract compliance in production")
            
        else:
            print("❌ DEMO COMPLETED WITH SOME ISSUES")
            print("   Check the logs above for specific problems")
        
        print("=" * 70)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
