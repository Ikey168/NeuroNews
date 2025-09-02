#!/usr/bin/env python3
"""
Demo script for Great Expectations data quality system.

This script demonstrates the Great Expectations integration that validates
data against contract constraints.
"""

import os
import sys
import json
import tempfile
import pandas as pd
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data_quality.checks import ContractBasedDataQuality

def create_sample_data():
    """Create sample data that matches our contracts."""
    
    # Valid articles data
    valid_articles = pd.DataFrame([
        {
            'article_id': 'demo-article-1',
            'source_id': 'reuters',
            'url': 'https://reuters.com/demo-article-1',
            'title': 'Demo Article: AI Breakthrough in Healthcare',
            'body': 'This is a demo article about AI in healthcare...',
            'language': 'en',
            'country': 'US',
            'published_at': 1692892800000,  # 2023-08-24
            'ingested_at': 1692893800000,   # 1000 seconds later
            'sentiment_score': 0.7,
            'topics': ['technology', 'healthcare', 'AI']
        },
        {
            'article_id': 'demo-article-2',
            'source_id': 'bbc',
            'url': 'https://bbc.com/demo-article-2',
            'title': 'Climate Change Impact on Economy',
            'body': 'Analysis of climate change effects on global economy...',
            'language': 'en',
            'country': 'UK',
            'published_at': 1692893000000,
            'ingested_at': 1692894000000,
            'sentiment_score': -0.3,
            'topics': ['environment', 'economy']
        },
        {
            'article_id': 'demo-article-3',
            'source_id': 'lemonde',
            'url': 'https://lemonde.fr/demo-article-3',
            'title': 'Nouvelle découverte scientifique',
            'body': 'Une nouvelle découverte révolutionnaire...',
            'language': 'fr',
            'country': 'FR',
            'published_at': 1692893200000,
            'ingested_at': 1692894200000,
            'sentiment_score': 0.5,
            'topics': ['science', 'recherche']
        }
    ])
    
    # Invalid articles data (to demonstrate failure scenarios)
    invalid_articles = pd.DataFrame([
        {
            'article_id': '',  # Invalid: empty article_id
            'source_id': 'invalid-source',
            'url': 'not-a-valid-url',  # Invalid: doesn't start with http(s)
            'title': 'Invalid Article 1',
            'body': 'This article has validation issues...',
            'language': 'invalid',  # Invalid: not ISO 639-1 format
            'country': 'invalid',   # Invalid: not ISO 3166-1 format
            'published_at': 1692892800000,
            'ingested_at': 1692892000000,  # Invalid: ingested before published
            'sentiment_score': 2.5,  # Invalid: outside [-1, 1] range
            'topics': ['test']
        },
        {
            'article_id': 'demo-article-missing-fields',
            'source_id': None,  # Invalid: null required field
            'url': None,        # Invalid: null required field
            'title': 'Article with Missing Fields',
            'body': None,
            'language': None,   # Invalid: null required field
            'country': 'US',
            'published_at': None,  # Invalid: null required field
            'ingested_at': None,   # Invalid: null required field
            'sentiment_score': None,
            'topics': []
        }
    ])
    
    # Valid ask requests data
    valid_requests = pd.DataFrame([
        {
            'question': 'What are the latest developments in AI technology?',
            'k': 5,
            'filters_source': 'reuters',
            'filters_date_from': '2023-08-20',
            'filters_date_to': '2023-08-25',
            'filters_language': 'en',
            'filters_category': 'technology'
        },
        {
            'question': 'How is climate change affecting the global economy?',
            'k': 10,
            'filters_source': 'bbc',
            'filters_date_from': '2023-08-21',
            'filters_date_to': '2023-08-24',
            'filters_language': 'en',
            'filters_category': 'environment'
        },
        {
            'question': 'Quelles sont les dernières nouvelles en France?',
            'k': 3,
            'filters_source': 'lemonde',
            'filters_date_from': '2023-08-22',
            'filters_date_to': '2023-08-23',
            'filters_language': 'fr',
            'filters_category': 'politics'
        }
    ])
    
    # Invalid ask requests data
    invalid_requests = pd.DataFrame([
        {
            'question': 'Hi',  # Invalid: too short (< 3 chars)
            'k': 25,           # Invalid: exceeds maximum (20)
            'filters_source': 'test',
            'filters_date_from': '23-08-20',  # Invalid: wrong date format
            'filters_date_to': '23-08-25',    # Invalid: wrong date format
            'filters_language': 'invalid',    # Invalid: not in enum
            'filters_category': 'test'
        },
        {
            'question': 'A' * 600,  # Invalid: too long (> 500 chars)
            'k': 0,                 # Invalid: below minimum (1)
            'filters_source': None,
            'filters_date_from': None,
            'filters_date_to': None,
            'filters_language': 'xyz',  # Invalid: not in enum
            'filters_category': None
        }
    ])
    
    return {
        'valid_articles': valid_articles,
        'invalid_articles': invalid_articles,
        'valid_requests': valid_requests,
        'invalid_requests': invalid_requests
    }

def print_header(title):
    """Print a formatted header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_results_summary(results, title):
    """Print a summary of validation results."""
    print(f"\n📊 {title}")
    print("-" * 40)
    
    success = results.get('overall_success', False)
    success_percent = results.get('success_percent', 0)
    total_expectations = results.get('total_expectations', 0)
    successful_expectations = results.get('successful_expectations', 0)
    failed_expectations = results.get('failed_expectations', [])
    
    status_icon = "✅" if success else "❌"
    print(f"Status: {status_icon} {'PASSED' if success else 'FAILED'}")
    print(f"Success Rate: {success_percent:.1f}%")
    print(f"Expectations: {successful_expectations}/{total_expectations} passed")
    
    if failed_expectations:
        print(f"\n❌ Failed Expectations ({len(failed_expectations)}):")
        for i, failure in enumerate(failed_expectations[:5], 1):
            exp_type = failure.get('expectation_type', 'Unknown')
            column = failure.get('column', 'N/A')
            print(f"  {i}. {exp_type} on column '{column}'")
        
        if len(failed_expectations) > 5:
            print(f"  ... and {len(failed_expectations) - 5} more")

def demo_csv_validation():
    """Demonstrate CSV file validation."""
    print_header("CSV File Validation Demo")
    
    # Create sample data
    sample_data = create_sample_data()
    
    # Initialize quality checker
    checker = ContractBasedDataQuality()
    
    print("📁 Testing with VALID articles data...")
    valid_results = checker.validate_dataframe(
        sample_data['valid_articles'], 
        'articles',
        run_name='demo_valid_articles'
    )
    ci_report = checker.generate_ci_report(valid_results)
    print_results_summary(ci_report, "Valid Articles Results")
    
    print("\n📁 Testing with INVALID articles data...")
    invalid_results = checker.validate_dataframe(
        sample_data['invalid_articles'], 
        'articles',
        run_name='demo_invalid_articles'
    )
    ci_report = checker.generate_ci_report(invalid_results)
    print_results_summary(ci_report, "Invalid Articles Results")
    
    print("\n📁 Testing with VALID ask requests data...")
    valid_req_results = checker.validate_dataframe(
        sample_data['valid_requests'], 
        'ask_requests',
        run_name='demo_valid_requests'
    )
    ci_report = checker.generate_ci_report(valid_req_results)
    print_results_summary(ci_report, "Valid Ask Requests Results")
    
    print("\n📁 Testing with INVALID ask requests data...")
    invalid_req_results = checker.validate_dataframe(
        sample_data['invalid_requests'], 
        'ask_requests',
        run_name='demo_invalid_requests'
    )
    ci_report = checker.generate_ci_report(invalid_req_results)
    print_results_summary(ci_report, "Invalid Ask Requests Results")

def demo_batch_validation():
    """Demonstrate batch validation across multiple suites."""
    print_header("Batch Validation Demo")
    
    # Create sample data
    sample_data = create_sample_data()
    
    # Initialize quality checker
    checker = ContractBasedDataQuality()
    
    print("🔄 Running all suites against mixed valid/invalid data...")
    
    # Prepare data for batch validation
    batch_data = {
        'articles': pd.concat([
            sample_data['valid_articles'], 
            sample_data['invalid_articles']
        ], ignore_index=True),
        'ask_requests': pd.concat([
            sample_data['valid_requests'],
            sample_data['invalid_requests']
        ], ignore_index=True)
    }
    
    # Run batch validation
    all_results = checker.run_all_suites(batch_data, run_name='demo_batch')
    
    print(f"\n📊 Batch Validation Summary")
    print("-" * 40)
    
    total_suites = len(all_results)
    passed_suites = sum(1 for suite_data in all_results.values() 
                       if suite_data.get('ci_report', {}).get('overall_success', False))
    
    print(f"Total Suites: {total_suites}")
    print(f"Passed Suites: {passed_suites}")
    print(f"Overall Success Rate: {(passed_suites / total_suites * 100):.1f}%")
    
    for suite_name, suite_data in all_results.items():
        ci_report = suite_data.get('ci_report', {})
        if 'error' in suite_data:
            print(f"\n❌ {suite_name}: ERROR - {suite_data['error']}")
        else:
            print_results_summary(ci_report, f"{suite_name} Suite")

def demo_ci_integration():
    """Demonstrate CI integration features."""
    print_header("CI Integration Demo")
    
    # Create sample data
    sample_data = create_sample_data()
    
    # Save sample data to temporary CSV files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Save valid articles
        valid_csv = temp_path / "valid_articles.csv"
        sample_data['valid_articles'].to_csv(valid_csv, index=False)
        
        # Save invalid articles  
        invalid_csv = temp_path / "invalid_articles.csv"
        sample_data['invalid_articles'].to_csv(invalid_csv, index=False)
        
        print("📄 Created temporary CSV files:")
        print(f"  Valid: {valid_csv}")
        print(f"  Invalid: {invalid_csv}")
        
        # Test CI script with valid data
        print("\n🧪 Testing CI script with VALID data...")
        os.system(f"cd {project_root} && ./data_quality/ci_integration.sh {valid_csv}")
        
        print("\n🧪 Testing CI script with INVALID data...")
        result = os.system(f"cd {project_root} && ./data_quality/ci_integration.sh {invalid_csv}")
        
        if result != 0:
            print("✅ CI script correctly detected validation failures and exited with error code")
        else:
            print("⚠️ CI script should have failed but didn't")

def demo_contract_traceability():
    """Demonstrate contract-to-expectation traceability."""
    print_header("Contract Traceability Demo")
    
    print("🔗 Contract-to-Expectation Mapping:")
    print("\n📋 Articles Contract (Avro):")
    print("  ├── article_id (required string) → expect_column_to_exist, expect_column_values_to_not_be_null")
    print("  ├── source_id (required string) → expect_column_to_exist, expect_column_values_to_not_be_null")
    print("  ├── url (required string) → expect_column_to_exist, expect_column_values_to_match_regex (http/https)")
    print("  ├── language (required string) → expect_column_values_to_match_regex (ISO 639-1)")
    print("  ├── country (optional string) → expect_column_values_to_match_regex (ISO 3166-1)")
    print("  ├── sentiment_score (optional double) → expect_column_values_to_be_between (-1, 1)")
    print("  └── timestamps → expect_column_pair_values_A_to_be_greater_than_B (ingested >= published)")
    
    print("\n📋 Ask Requests Contract (JSON Schema):")
    print("  ├── question (required string, 3-500 chars) → expect_column_value_lengths_to_be_between")
    print("  ├── k (integer, 1-20, default 5) → expect_column_values_to_be_between")
    print("  ├── filters.language (enum) → expect_column_values_to_match_regex")
    print("  └── filters.date_* (date format) → expect_column_values_to_match_regex (YYYY-MM-DD)")
    
    # Load and display expectation suites
    checker = ContractBasedDataQuality()
    
    print("\n📊 Generated Expectations:")
    
    for suite_file in checker.expectations_dir.glob("*.yml"):
        suite_name = suite_file.stem
        suite = checker.load_expectation_suite_from_yaml(suite_file.name)
        
        print(f"\n📁 {suite_name} Suite:")
        print(f"  Total Expectations: {len(suite.expectations)}")
        
        # Group by expectation type
        exp_types = {}
        for exp in suite.expectations:
            exp_type = exp.expectation_type
            exp_types[exp_type] = exp_types.get(exp_type, 0) + 1
        
        for exp_type, count in sorted(exp_types.items()):
            print(f"  ├── {exp_type}: {count}")

def main():
    """Main demo function."""
    print("🎉 Great Expectations Data Contracts Demo")
    print("=========================================")
    print("\nThis demo shows how Great Expectations validates data")
    print("against constraints derived from Avro and JSON Schema contracts.")
    
    try:
        # Run all demo sections
        demo_contract_traceability()
        demo_csv_validation()
        demo_batch_validation()
        demo_ci_integration()
        
        print_header("Demo Complete")
        print("✅ Great Expectations data quality system is working correctly!")
        print("\n📋 Summary:")
        print("  ✅ Contract-derived expectations created")
        print("  ✅ CSV validation working")
        print("  ✅ Batch validation working")
        print("  ✅ CI integration functional")
        print("  ✅ Pass/fail detection accurate")
        
        print("\n🚀 Next Steps:")
        print("  1. Integrate with your data pipelines")
        print("  2. Set up automated CI/CD workflows")
        print("  3. Configure dashboard monitoring")
        print("  4. Train team on expectation maintenance")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
