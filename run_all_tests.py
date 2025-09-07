#!/usr/bin/env python3
"""
Unified Test Runner for NeuroNews
Runs all available test systems in the repository with proper error handling.
"""

import os
import sys
import subprocess
from pathlib import Path
import importlib.util

# Add src directory to Python path to help with imports
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))


class TestRunner:
    """Main test runner that orchestrates all test systems."""
    
    def __init__(self):
        self.passed_tests = []
        self.failed_tests = []
        self.skipped_tests = []
        
    def run_python_script(self, script_path, description):
        """Run a Python script and capture its result."""
        print(f"\n{'='*60}")
        print(f"🔍 Running: {description}")
        print(f"📁 Script: {script_path}")
        print('='*60)
        
        try:
            if not Path(script_path).exists():
                print(f"❌ Script not found: {script_path}")
                self.failed_tests.append((description, "Script not found"))
                return False
                
            # Run the script in a subprocess
            result = subprocess.run(
                [sys.executable, script_path], 
                cwd=os.getcwd(),
                capture_output=False,  # Let output show in real time
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ {description} - PASSED")
                self.passed_tests.append(description)
                return True
            else:
                print(f"❌ {description} - FAILED (exit code: {result.returncode})")
                self.failed_tests.append((description, f"Exit code: {result.returncode}"))
                return False
                
        except Exception as e:
            print(f"❌ {description} - ERROR: {e}")
            self.failed_tests.append((description, str(e)))
            return False
    
    def run_pytest_tests(self, test_path, description):
        """Run pytest on a specific test path."""
        print(f"\n{'='*60}")
        print(f"🧪 Running: {description}")
        print(f"📁 Path: {test_path}")
        print('='*60)
        
        try:
            # Install pytest if not available
            try:
                import pytest
            except ImportError:
                print("📦 Installing pytest...")
                subprocess.run([sys.executable, "-m", "pip", "install", "pytest"], check=True)
                
            if not Path(test_path).exists():
                print(f"⚠️ Test path not found: {test_path}")
                self.skipped_tests.append((description, "Path not found"))
                return False
                
            # Run pytest
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v"],
                cwd=os.getcwd(),
                capture_output=False
            )
            
            if result.returncode == 0:
                print(f"✅ {description} - PASSED")
                self.passed_tests.append(description)
                return True
            else:
                print(f"❌ {description} - FAILED")
                self.failed_tests.append((description, "Pytest failed"))
                return False
                
        except Exception as e:
            print(f"❌ {description} - ERROR: {e}")
            self.failed_tests.append((description, str(e)))
            return False
    
    def run_all_tests(self):
        """Run all available test systems."""
        print("🚀 NeuroNews - Unified Test Runner")
        print("="*60)
        print("Running all available test systems...")
        
        # List of test systems to run
        test_systems = [
            # Main test runners
            ("run_modular_tests.py", "Modular Test Suite"),
            
            # Functional and integration tests
            ("tests/functional/test_issue_31_simple.py", "Issue #31 Functional Tests"),
            ("tests/integration/test_lambda_automation.py", "Lambda Automation Tests"),
            
            # ML and specialized tests
            ("scripts/run_ml_tests.py", "ML Module Tests"),
            ("tests/unit/test_dod_requirements.py", "DoD Requirements Tests"),
            ("scripts/utilities/quick_validation.py", "Quick Validation Tests"),
            
            # Additional test scripts
            ("scripts/test_imports.py", "Import Validation Tests"),
        ]
        
        # Optional pytest test directories
        pytest_tests = [
            ("tests/unit", "Unit Tests"),
            ("tests/integration", "Integration Tests (pytest)"),
        ]
        
        # Run Python script-based tests
        for script_path, description in test_systems:
            self.run_python_script(script_path, description)
        
        # Run pytest-based tests for directories that exist
        for test_path, description in pytest_tests:
            if Path(test_path).exists():
                # Check if there are any .py files in the directory
                py_files = list(Path(test_path).rglob("*.py"))
                if py_files:
                    self.run_pytest_tests(test_path, description)
                else:
                    print(f"⚠️ Skipping {description} - no Python files found")
                    self.skipped_tests.append((description, "No Python files"))
            else:
                print(f"⚠️ Skipping {description} - directory not found")
                self.skipped_tests.append((description, "Directory not found"))
        
        # Print final summary
        self.print_summary()
        
        # Return overall success
        return len(self.failed_tests) == 0
    
    def print_summary(self):
        """Print final test summary."""
        print(f"\n{'='*80}")
        print("🏁 TEST EXECUTION SUMMARY")
        print('='*80)
        
        total_tests = len(self.passed_tests) + len(self.failed_tests) + len(self.skipped_tests)
        
        print(f"📊 Total Test Systems: {total_tests}")
        print(f"✅ Passed: {len(self.passed_tests)}")
        print(f"❌ Failed: {len(self.failed_tests)}")
        print(f"⚠️ Skipped: {len(self.skipped_tests)}")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS:")
            for test in self.passed_tests:
                print(f"  ✓ {test}")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for test, reason in self.failed_tests:
                print(f"  ✗ {test} - {reason}")
        
        if self.skipped_tests:
            print(f"\n⚠️ SKIPPED TESTS:")
            for test, reason in self.skipped_tests:
                print(f"  ~ {test} - {reason}")
        
        success_rate = (len(self.passed_tests) / total_tests * 100) if total_tests > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        if len(self.failed_tests) == 0:
            print("🎉 ALL RUNNABLE TESTS PASSED!")
        else:
            print("⚠️ Some tests failed - but all are now runnable!")


def main():
    """Main entry point."""
    runner = TestRunner()
    success = runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())