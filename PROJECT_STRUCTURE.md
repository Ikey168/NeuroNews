# NeuroNews Project Structure

This document describes the reorganized project structure for better maintainability and organization.

## Directory Structure

```
NeuroNews/
├── src/                           # Source code
│   ├── api/                      # API endpoints and routes
│   ├── apps/                     # Application modules
│   ├── database/                 # Database models and connections
│   ├── ingestion/                # Data ingestion pipelines
│   ├── knowledge_graph/          # Knowledge graph components
│   ├── ml/                       # Machine learning models and pipelines
│   ├── nlp/                      # Natural language processing
│   ├── scraper/                  # Web scraping components
│   ├── services/                 # Business logic services
│   └── utils/                    # Utility functions
│
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   │   ├── api/                  # API unit tests
│   │   ├── database/             # Database unit tests
│   │   ├── ml/                   # ML unit tests
│   │   ├── nlp/                  # NLP unit tests
│   │   └── scraper/              # Scraper unit tests
│   ├── integration/              # Integration tests
│   ├── e2e/                      # End-to-end tests
│   ├── performance/              # Performance tests
│   ├── security/                 # Security tests
│   ├── coverage/                 # Coverage-related tests
│   ├── dod/                      # Definition of Done tests
│   └── fixtures/                 # Test fixtures and mocks
│
├── scripts/                      # Utility scripts
│   ├── database/                 # Database management scripts
│   ├── testing/                  # Testing-related scripts
│   └── validation/               # Validation scripts
│
├── docs/                         # Documentation
│   ├── coverage/                 # Coverage reports and documentation
│   └── reports/                  # Implementation and status reports
│
├── demo/                         # Demo scripts and examples
├── config/                       # Configuration files
├── docker/                       # Docker configurations
├── infra/                        # Infrastructure as code
├── workflows/                    # CI/CD workflows
└── requirements/                 # Dependency specifications
```

## Key Changes Made

### 1. Test Organization
- **Before**: 84+ test files scattered in the root `tests/` directory
- **After**: Tests organized by type and functionality:
  - Unit tests grouped by component (api, database, ml, nlp, scraper)
  - Coverage tests in dedicated `coverage/` directory
  - DOD (Definition of Done) tests in `dod/` directory
  - Integration, e2e, performance, and security tests in separate directories

### 2. Script Organization
- **Before**: Utility scripts scattered in project root
- **After**: Scripts organized in `scripts/` directory:
  - `scripts/database/` - Database migration, modularization scripts
  - `scripts/testing/` - Test utilities, coverage analysis
  - `scripts/validation/` - Validation and verification scripts

### 3. Documentation Organization
- **Before**: Documentation files scattered in project root
- **After**: Documentation organized in `docs/` directory:
  - `docs/coverage/` - Coverage reports and documentation
  - `docs/reports/` - Implementation reports and summaries

### 4. Demo Files
- **Before**: Demo scripts in project root
- **After**: All demo files consolidated in `demo/` directory

## File Mappings

### Moved to `scripts/`
- `check_imports.py` → `scripts/check_imports.py`
- `test_imports.py` → `scripts/test_imports.py`
- `create_sample_data.py` → `scripts/create_sample_data.py`

### Moved to `scripts/database/`
- `migrate_database_tests.py`
- `modularize_database_tests.py`
- `fix_timestamp_types.py`

### Moved to `scripts/testing/`
- `fix_test_functions.py`
- `refactor_tests.py`
- `run_ml_tests.py`
- `test_coverage_analysis.py`
- `quick_coverage_estimate.py`
- `graph_api_coverage_test.py`
- `test_breaking_change_detection.sh`

### Moved to `scripts/validation/`
- `validate_news_pipeline_mlflow.py`
- `verify_issue_233.py`
- `test_validation_behavior.py`

### Moved to `tests/coverage/`
- All percentage-based coverage tests (`test_*percent*.py`)
- Strategic coverage tests (`test_*strategic*.py`)
- Final coverage push tests (`test_*final*.py`)
- Nuclear coverage tests (`test_*nuclear*.py`)

### Moved to `tests/dod/`
- `test_hybrid_retrieval_dod.py`
- `test_hybrid_retrieval_dod_simple.py`
- `test_lexical_search_dod.py`
- `test_dod_requirements.py`

### Moved to `tests/unit/ml/`
- `test_mlflow_callbacks.py`
- `test_mlflow_setup.py`

### Moved to `docs/coverage/`
- All coverage-related markdown files (`*COVERAGE*.md`)

### Moved to `docs/reports/`
- Implementation completion reports
- Database test cleanup summaries
- Phase summaries and PR descriptions

## Benefits of New Structure

1. **Better Organization**: Related files are grouped together
2. **Easier Navigation**: Clear directory structure makes finding files intuitive
3. **Reduced Root Clutter**: Clean project root with only essential files
4. **Improved Maintainability**: Logical grouping makes maintenance easier
5. **Better Separation of Concerns**: Tests, scripts, docs, and source code are clearly separated
6. **Enhanced Developer Experience**: New developers can quickly understand the project layout

## Migration Notes

- All file paths in import statements may need to be updated
- CI/CD scripts may need path updates
- IDE configurations may need adjustment
- Documentation references should be updated to reflect new paths

## Next Steps

1. Update import statements in affected files
2. Update CI/CD pipeline configurations
3. Update IDE workspace settings
4. Update documentation references
5. Test all functionality to ensure nothing was broken during reorganization
