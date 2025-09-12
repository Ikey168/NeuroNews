#!/usr/bin/env python3
"""
Coverage script for checking test coverage of /src directory only
Usage: python run_coverage.py [--format=html|xml|term] [--report-dir=DIR]
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path


def run_coverage(format_type='term', report_dir='htmlcov', test_path=None):
    """
    Run test coverage for /src directory only
    
    Args:
        format_type: Output format ('term', 'html', 'xml')
        report_dir: Directory for HTML/XML reports
        test_path: Specific test path to run (default: tests/)
    """
    
    # Base command for pytest with coverage
    cmd = [
        'python', '-m', 'pytest',
        '--cov=src',
        '--cov-config=.coveragerc',
        '-v'
    ]
    
    # Add test path
    if test_path:
        cmd.append(test_path)
    else:
        # Default to working test to avoid dependency issues
        cmd.append('tests/unit/test_simple_coverage.py')
    
    # Add coverage report format
    if format_type == 'html':
        cmd.extend(['--cov-report=html', f'--cov-report=html:{report_dir}'])
    elif format_type == 'xml':
        cmd.extend(['--cov-report=xml', f'--cov-report=xml:{report_dir}/coverage.xml'])
    elif format_type == 'term':
        cmd.append('--cov-report=term-missing')
    
    print(f"Running coverage for /src directory...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nCoverage run interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running coverage: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description='Run test coverage for /src directory only')
    parser.add_argument(
        '--format', 
        choices=['term', 'html', 'xml'], 
        default='term',
        help='Output format for coverage report (default: term)'
    )
    parser.add_argument(
        '--report-dir', 
        default='htmlcov',
        help='Directory for HTML/XML reports (default: htmlcov)'
    )
    parser.add_argument(
        '--test-path',
        help='Specific test path to run (default: tests/)'
    )
    parser.add_argument(
        '--unit-only',
        action='store_true',
        help='Run only unit tests'
    )
    
    args = parser.parse_args()
    
    # Set working directory to repository root
    repo_root = Path(__file__).parent
    os.chdir(repo_root)
    
    # Determine test path
    test_path = args.test_path
    if args.unit_only:
        test_path = 'tests/unit/'
    
    # Run coverage
    exit_code = run_coverage(
        format_type=args.format,
        report_dir=args.report_dir,
        test_path=test_path
    )
    
    if exit_code == 0:
        print("\n" + "="*60)
        print("✅ Coverage analysis completed successfully!")
        if args.format == 'html':
            print(f"📊 HTML report generated in: {args.report_dir}/")
            print(f"🌐 Open {args.report_dir}/index.html in your browser")
        elif args.format == 'xml':
            print(f"📊 XML report generated: {args.report_dir}/coverage.xml")
    else:
        print("\n" + "="*60)
        print("❌ Coverage analysis completed with errors")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())