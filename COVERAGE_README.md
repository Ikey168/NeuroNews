# Test Coverage for /src Directory

This repository is configured to check test coverage specifically for the `/src` directory only. This document explains how to run and analyze test coverage.

## Quick Start

### Using the Coverage Script
```bash
# Run coverage with terminal output
python run_coverage.py

# Generate HTML coverage report
python run_coverage.py --format=html

# Run coverage on unit tests only
python run_coverage.py --unit-only

# Run coverage on specific test file
python run_coverage.py --test-path=tests/unit/test_simple_coverage.py
```

### Using Make Commands
```bash
# Show available commands
make -f Makefile_coverage help

# Run coverage with terminal output
make -f Makefile_coverage coverage

# Generate HTML coverage report
make -f Makefile_coverage coverage-html

# Run coverage on unit tests only  
make -f Makefile_coverage coverage-unit

# Run working tests with coverage
make -f Makefile_coverage test

# Clean coverage reports and cache
make -f Makefile_coverage clean
```

## Configuration

### Coverage Configuration (`.coveragerc`)
The coverage is configured to focus exclusively on the `/src` directory:
- **Source**: Only files in `src/` are included in coverage analysis
- **Exclusions**: Test files, migrations, scripts, demos, and `__init__.py` files are excluded
- **Output**: HTML reports are generated in `htmlcov/` directory

### Pytest Configuration (`pytest.ini`)
The pytest configuration includes:
- Coverage configuration reference to `.coveragerc`
- Test path set to `tests/`
- Various test markers for categorization

## Coverage Outputs

### Terminal Output
Shows a detailed table with:
- File names from `/src` directory
- Total statements per file
- Missed statements
- Coverage percentage
- Missing line numbers

### HTML Report
Generates an interactive HTML report in `htmlcov/`:
- Overall coverage statistics
- File-by-file coverage details  
- Line-by-line coverage highlighting
- Function and class coverage details

### XML Report
Generates machine-readable XML coverage data suitable for CI/CD integration.

## Current Coverage Status

As of the last run, the repository has approximately **1% test coverage** for the `/src` directory. This low coverage is primarily due to:

1. **Dependency Issues**: Many tests fail to import due to missing dependencies (networkx, streamlit, mlflow, etc.)
2. **Test Infrastructure**: Most existing tests have dependency conflicts
3. **Large Codebase**: The `/src` directory contains over 41,000 lines of code across hundreds of files

## Working Test Example

A working test example is provided in `tests/unit/test_simple_coverage.py` that demonstrates:
- Basic import testing of the `config.py` module
- Functional testing of configuration methods
- Proper test structure for coverage analysis

## File Structure

```
├── .coveragerc              # Coverage configuration (src-only focus)
├── pytest.ini              # Pytest configuration
├── run_coverage.py          # Coverage script with multiple format options
├── Makefile_coverage        # Make targets for coverage commands
├── tests/
│   └── unit/
│       └── test_simple_coverage.py  # Working test example
└── src/                     # Source code directory (coverage target)
    ├── api/                 # API modules
    ├── config.py           # Configuration module (covered by tests)
    ├── services/           # Service modules
    └── ...                 # Other source modules
```

## Extending Test Coverage

To improve test coverage:

1. **Fix Dependencies**: Install missing packages (networkx, streamlit, mlflow, etc.)
2. **Create Unit Tests**: Add focused unit tests for individual modules
3. **Mock External Dependencies**: Use pytest mocking for external services
4. **Incremental Testing**: Start with simple modules and gradually expand

## Commands Reference

| Command | Description |
|---------|-------------|
| `python run_coverage.py` | Basic terminal coverage report |
| `python run_coverage.py --format=html` | Generate HTML report |
| `python run_coverage.py --format=xml` | Generate XML report |
| `python run_coverage.py --unit-only` | Run unit tests only |
| `python run_coverage.py --test-path=<path>` | Run specific test path |
| `make -f Makefile_coverage coverage` | Terminal coverage via make |
| `make -f Makefile_coverage coverage-html` | HTML coverage via make |
| `make -f Makefile_coverage clean` | Clean coverage artifacts |

## Notes

- Coverage is focused **exclusively on the `/src` directory**
- The configuration automatically excludes test files, scripts, and other non-source code
- HTML reports provide the most detailed coverage analysis
- Some files may show parsing warnings but this doesn't affect coverage calculation
- The current 1% coverage indicates significant opportunity for test improvement