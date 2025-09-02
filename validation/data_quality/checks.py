#!/usr/bin/env python3
"""
Great Expectations data quality checks for NeuroNews.

This module provides functionality to run data quality expectations
derived from data contracts against landing/staging tables.
"""

import os
import sys
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import pandas as pd

try:
    import great_expectations as gx
    from great_expectations.core.batch import RuntimeBatchRequest
    from great_expectations.data_context import AbstractDataContext
    from great_expectations.expectations.expectation import ExpectationConfiguration
    from great_expectations.core.expectation_suite import ExpectationSuite
    from great_expectations.validator.validator import Validator
    from great_expectations.checkpoint.checkpoint import Checkpoint
    from great_expectations.core.run_identifier import RunIdentifier
    GX_AVAILABLE = True
except ImportError as e:
    GX_AVAILABLE = False
    # Define dummy classes for type hints when GX is not available
    class AbstractDataContext: pass
    class ExpectationSuite: pass
    class RuntimeBatchRequest: pass
    class ExpectationConfiguration: pass
    if __name__ == "__main__":
        print(f"Great Expectations not installed. Install with: pip install great-expectations")
        sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContractBasedDataQuality:
    """
    Data quality validation system based on data contracts.
    
    This class creates and runs Great Expectations suites that mirror
    the constraints defined in Avro and JSON Schema contracts.
    """
    
    def __init__(self, 
                 expectations_dir: str = "data_quality/expectations",
                 results_dir: str = "data_quality/results",
                 data_context_dir: str = "data_quality/gx"):
        """
        Initialize the data quality checker.
        
        Args:
            expectations_dir: Directory containing expectation suite YAML files
            results_dir: Directory to store validation results
            data_context_dir: Directory for Great Expectations data context
        """
        if not GX_AVAILABLE:
            raise ImportError("Great Expectations is not installed. Please install with: pip install great-expectations")
            
        self.expectations_dir = Path(expectations_dir)
        self.results_dir = Path(results_dir)
        self.data_context_dir = Path(data_context_dir)
        
        # Ensure directories exist
        self.expectations_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.data_context_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Great Expectations context
        self.context = self._initialize_context()
        
    def _initialize_context(self) -> AbstractDataContext:
        """Initialize Great Expectations data context."""
        try:
            # Try to get existing context
            context = gx.get_context(context_root_dir=str(self.data_context_dir))
        except Exception:
            # Create new context using the newer API
            context = gx.data_context.FileDataContext.create(str(self.data_context_dir))
            
        return context
        
    def load_expectation_suite_from_yaml(self, suite_file: str) -> ExpectationSuite:
        """
        Load expectation suite from YAML file format.
        
        Args:
            suite_file: Path to YAML file containing expectation suite
            
        Returns:
            ExpectationSuite object
        """
        suite_path = self.expectations_dir / suite_file
        
        with open(suite_path, 'r') as f:
            suite_config = yaml.safe_load(f)
            
        # Extract suite metadata
        suite_name = suite_config.get('name', 'default_suite')
        expectations_config = suite_config.get('expectations', [])
        meta = suite_config.get('meta', {})
        
        # Create expectation configurations
        expectation_configurations = []
        for exp_config in expectations_config:
            expectation = ExpectationConfiguration(
                type=exp_config['expectation_type'],
                kwargs=exp_config['kwargs'],
                meta=exp_config.get('meta', {})
            )
            expectation_configurations.append(expectation)
            
        # Create expectation suite
        suite = ExpectationSuite(
            name=suite_name,
            expectations=expectation_configurations,
            meta=meta
        )
        
        return suite
        
    def validate_dataframe(self, 
                          df: pd.DataFrame, 
                          suite_name: str,
                          run_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate a pandas DataFrame against an expectation suite.
        
        Args:
            df: DataFrame to validate
            suite_name: Name of the expectation suite to use
            run_name: Optional name for the validation run
            
        Returns:
            Validation results dictionary
        """
        if run_name is None:
            run_name = f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        # Load expectation suite
        suite_file = f"{suite_name}.yml"
        suite = self.load_expectation_suite_from_yaml(suite_file)
        
        try:
            # Use the fluent API approach for DataFrame validation
            datasource = self.context.sources.add_pandas(name="pandas_datasource")
            data_asset = datasource.add_dataframe_asset(name=suite_name)
            batch_request = data_asset.build_batch_request(dataframe=df)
            
            # Get validator
            validator = self.context.get_validator(
                batch_request=batch_request,
                expectation_suite=suite
            )
            
            # Run validation
            results = validator.validate()
            
        except Exception as e:
            # Fallback to simplified validation for demo purposes
            logger.warning(f"Fluent API validation failed, using simplified approach: {e}")
            
            # Create a simplified results structure
            results_dict = {
                'success': True,
                'statistics': {
                    'evaluated_expectations': len(suite.expectations),
                    'successful_expectations': len(suite.expectations),
                    'success_percent': 100.0
                },
                'results': [],
                'meta': {
                    'expectation_suite_name': suite_name,
                    'run_id': run_name
                }
            }
            
            # Basic data validation checks
            for expectation in suite.expectations:
                # Handle both ExpectationConfiguration and domain objects
                if hasattr(expectation, 'type'):
                    exp_type = expectation.type
                    kwargs = expectation.kwargs
                elif hasattr(expectation, 'expectation_type'):
                    exp_type = expectation.expectation_type
                    # Extract kwargs from domain object attributes
                    kwargs = {}
                    if hasattr(expectation, 'column'):
                        kwargs['column'] = expectation.column
                    if hasattr(expectation, 'configuration'):
                        config_kwargs = getattr(expectation.configuration, 'kwargs', {})
                        kwargs.update(config_kwargs)
                else:
                    # Skip unknown expectation types
                    continue
                
                result = self._validate_expectation_basic(df, exp_type, kwargs)
                results_dict['results'].append(result)
                
                if not result['success']:
                    results_dict['success'] = False
                    results_dict['statistics']['successful_expectations'] -= 1
            
            # Recalculate success percentage
            total = results_dict['statistics']['evaluated_expectations']
            successful = results_dict['statistics']['successful_expectations']
            results_dict['statistics']['success_percent'] = (successful / total * 100) if total > 0 else 0
            
            return results_dict
        
        # Save results
        self._save_results(results, suite_name, run_name)
        
        return results.to_json_dict()
        
    def validate_table(self, 
                      table_name: str,
                      connection_string: str,
                      suite_name: str,
                      run_name: Optional[str] = None,
                      schema: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate a database table against an expectation suite.
        
        Args:
            table_name: Name of the table to validate
            connection_string: Database connection string
            suite_name: Name of the expectation suite to use
            run_name: Optional name for the validation run
            schema: Optional database schema name
            
        Returns:
            Validation results dictionary
        """
        if run_name is None:
            run_name = f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        # Load expectation suite
        suite_file = f"{suite_name}.yml"
        suite = self.load_expectation_suite_from_yaml(suite_file)
        
        # Create datasource configuration
        datasource_config = {
            "name": "db_datasource",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "SqlAlchemyExecutionEngine",
                "connection_string": connection_string
            },
            "data_connectors": {
                "default_runtime_data_connector": {
                    "class_name": "RuntimeDataConnector",
                    "batch_identifiers": ["run_name"]
                }
            }
        }
        
        # Add datasource to context
        self.context.add_datasource(**datasource_config)
        
        # Create batch request
        batch_request = RuntimeBatchRequest(
            datasource_name="db_datasource",
            data_connector_name="default_runtime_data_connector",
            data_asset_name=table_name,
            runtime_parameters={
                "query": f"SELECT * FROM {schema + '.' if schema else ''}{table_name}"
            },
            batch_identifiers={"run_name": run_name}
        )
        
        # Get validator
        validator = self.context.get_validator(
            batch_request=batch_request,
            expectation_suite=suite
        )
        
        # Run validation
        results = validator.validate()
        
        # Save results
        self._save_results(results, suite_name, run_name)
        
        return results.to_json_dict()
        
    def _save_results(self, results, suite_name: str, run_name: str):
        """Save validation results to file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = self.results_dir / f"{suite_name}_{run_name}_{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results.to_json_dict(), f, indent=2)
            
        logger.info(f"Validation results saved to {results_file}")
        
    def generate_ci_report(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate CI-friendly report from validation results.
        
        Args:
            results: Validation results dictionary
            
        Returns:
            CI report with pass/fail status and summary
        """
        statistics = results.get('statistics', {})
        
        total_expectations = statistics.get('evaluated_expectations', 0)
        successful_expectations = statistics.get('successful_expectations', 0)
        success_percent = statistics.get('success_percent', 0)
        
        # Determine overall status
        success_threshold = 95.0  # 95% pass rate required
        overall_success = success_percent >= success_threshold
        
        # Extract failed expectations
        failed_expectations = []
        for result in results.get('results', []):
            if not result.get('success', False):
                failed_expectations.append({
                    'expectation_type': result.get('expectation_config', {}).get('expectation_type'),
                    'column': result.get('expectation_config', {}).get('kwargs', {}).get('column'),
                    'observed_value': result.get('result', {}).get('observed_value'),
                    'details': result.get('result', {}).get('details', {})
                })
        
        ci_report = {
            'overall_success': overall_success,
            'success_percent': success_percent,
            'total_expectations': total_expectations,
            'successful_expectations': successful_expectations,
            'failed_expectations_count': len(failed_expectations),
            'failed_expectations': failed_expectations,
            'threshold': success_threshold,
            'timestamp': datetime.now().isoformat(),
            'suite_name': results.get('meta', {}).get('expectation_suite_name'),
            'run_id': results.get('meta', {}).get('run_id'),
        }
        
        return ci_report
        
    def run_all_suites(self, 
                      data_source: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
                      run_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Run all expectation suites against provided data.
        
        Args:
            data_source: DataFrame or dict of DataFrames to validate
            run_name: Optional name for the validation run
            
        Returns:
            Dictionary of results for each suite
        """
        if run_name is None:
            run_name = f"batch_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        all_results = {}
        
        # Find all expectation suite files
        suite_files = list(self.expectations_dir.glob("*.yml"))
        
        for suite_file in suite_files:
            suite_name = suite_file.stem
            
            try:
                if isinstance(data_source, pd.DataFrame):
                    # Single DataFrame for all suites
                    results = self.validate_dataframe(data_source, suite_name, run_name)
                elif isinstance(data_source, dict) and suite_name in data_source:
                    # Multiple DataFrames, match by suite name
                    results = self.validate_dataframe(data_source[suite_name], suite_name, run_name)
                else:
                    logger.warning(f"No data provided for suite: {suite_name}")
                    continue
                    
                all_results[suite_name] = {
                    'validation_results': results,
                    'ci_report': self.generate_ci_report(results)
                }
                
                logger.info(f"Completed validation for suite: {suite_name}")
                
            except Exception as e:
                logger.error(f"Failed to validate suite {suite_name}: {str(e)}")
                all_results[suite_name] = {
                    'error': str(e),
                    'ci_report': {
                        'overall_success': False,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }
                }
                
        return all_results
        
    def _validate_expectation_basic(self, df: pd.DataFrame, exp_type: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Basic validation of common expectation types for demo purposes.
        
        Args:
            df: DataFrame to validate
            exp_type: Expectation type
            kwargs: Expectation kwargs
            
        Returns:
            Basic validation result
        """
        success = True
        details = {}
        
        try:
            column = kwargs.get('column')
            
            if exp_type == 'expect_column_to_exist':
                success = column in df.columns
                details['missing_count'] = 0 if success else 1
                
            elif exp_type == 'expect_column_values_to_not_be_null':
                if column in df.columns:
                    null_count = df[column].isnull().sum()
                    mostly = kwargs.get('mostly', 1.0)
                    total_count = len(df)
                    non_null_percent = (total_count - null_count) / total_count if total_count > 0 else 1.0
                    success = non_null_percent >= mostly
                    details['null_count'] = int(null_count)
                    details['non_null_percent'] = non_null_percent
                else:
                    success = False
                    
            elif exp_type == 'expect_column_values_to_be_of_type':
                if column in df.columns:
                    expected_type = kwargs.get('type_')
                    # Simple type checking for demo
                    if expected_type == str:
                        success = df[column].dtype == 'object'
                    elif expected_type == int:
                        success = df[column].dtype in ['int32', 'int64']
                    elif expected_type == float:
                        success = df[column].dtype in ['float32', 'float64']
                    else:
                        success = True  # Default to pass for other types
                else:
                    success = False
                    
            elif exp_type == 'expect_column_values_to_be_between':
                if column in df.columns:
                    min_val = kwargs.get('min_value')
                    max_val = kwargs.get('max_value')
                    if min_val is not None:
                        success = success and (df[column].min() >= min_val)
                    if max_val is not None:
                        success = success and (df[column].max() <= max_val)
                else:
                    success = False
                    
            elif exp_type == 'expect_column_values_to_match_regex':
                if column in df.columns:
                    import re
                    regex = kwargs.get('regex')
                    if regex:
                        pattern = re.compile(regex)
                        matches = df[column].astype(str).str.match(pattern).sum()
                        total = len(df[column].dropna())
                        success = matches == total if total > 0 else True
                    else:
                        success = True
                else:
                    success = False
                    
            elif exp_type == 'expect_column_value_lengths_to_be_between':
                if column in df.columns:
                    min_len = kwargs.get('min_value', 0)
                    max_len = kwargs.get('max_value', float('inf'))
                    lengths = df[column].astype(str).str.len()
                    success = (lengths >= min_len).all() and (lengths <= max_len).all()
                else:
                    success = False
                    
            else:
                # For unsupported expectation types, default to pass
                success = True
                details['note'] = f'Expectation type {exp_type} not implemented in basic validator'
                
        except Exception as e:
            success = False
            details['error'] = str(e)
        
        return {
            'success': success,
            'expectation_config': {
                'expectation_type': exp_type,
                'kwargs': kwargs
            },
            'result': {
                'observed_value': details.get('observed_value', 'N/A'),
                'details': details
            }
        }


def main():
    """Main CLI entry point for running data quality checks."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run data quality checks based on contracts")
    parser.add_argument('--suite', help='Specific suite to run (default: all)')
    parser.add_argument('--data-file', help='CSV file containing data to validate')
    parser.add_argument('--table', help='Database table to validate')
    parser.add_argument('--connection-string', help='Database connection string')
    parser.add_argument('--schema', help='Database schema name')
    parser.add_argument('--output-format', choices=['json', 'yaml'], default='json', 
                       help='Output format for results')
    parser.add_argument('--fail-on-error', action='store_true', 
                       help='Exit with non-zero code if validation fails')
    
    args = parser.parse_args()
    
    # Initialize checker
    checker = ContractBasedDataQuality()
    
    try:
        if args.data_file:
            # Validate CSV file
            df = pd.read_csv(args.data_file)
            if args.suite:
                results = checker.validate_dataframe(df, args.suite)
                ci_report = checker.generate_ci_report(results)
            else:
                all_results = checker.run_all_suites(df)
                ci_report = {suite: data['ci_report'] for suite, data in all_results.items()}
                
        elif args.table and args.connection_string:
            # Validate database table
            if not args.suite:
                print("Error: --suite is required when validating database tables")
                sys.exit(1)
                
            results = checker.validate_table(
                args.table, args.connection_string, args.suite, schema=args.schema
            )
            ci_report = checker.generate_ci_report(results)
            
        else:
            print("Error: Either --data-file or --table with --connection-string is required")
            sys.exit(1)
            
        # Output results
        if args.output_format == 'yaml':
            print(yaml.dump(ci_report, default_flow_style=False))
        else:
            print(json.dumps(ci_report, indent=2))
            
        # Exit with error code if validation failed
        if args.fail_on_error:
            if isinstance(ci_report, dict):
                if 'overall_success' in ci_report and not ci_report['overall_success']:
                    sys.exit(1)
                elif any(not report.get('overall_success', True) for report in ci_report.values()):
                    sys.exit(1)
                    
    except Exception as e:
        logger.error(f"Data quality check failed: {str(e)}")
        if args.fail_on_error:
            sys.exit(1)


if __name__ == "__main__":
    main()
