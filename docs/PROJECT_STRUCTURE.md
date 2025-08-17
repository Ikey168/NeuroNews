# Project Structure

## Overview
NeuroNews is organized into the following directories:

```
NeuroNews/
├── .github/                    # GitHub Actions workflows and templates
├── config/                     # Configuration files
├── data/                      # Data storage and datasets
├── demo/                      # Demo scripts and examples
│   ├── results/              # Demo output and results
├── deployment/               # Deployment configurations and scripts
├── docs/                     # Documentation
│   ├── guides/              # User and developer guides
│   ├── implementation/      # Implementation documentation
│   └── reports/             # Progress reports and summaries
├── logs/                     # Application and system logs
├── scripts/                  # Utility and automation scripts
├── src/                      # Main source code
├── tests/                    # Test suite
├── validation/               # Validation scripts and utilities
├── docker-compose*.yml       # Docker Compose configurations
├── Dockerfile*               # Docker build configurations
├── requirements*.txt         # Python dependencies
└── pyproject.toml           # Python project configuration
```

## Directory Descriptions

### `/src/` - Source Code
Main application source code including:
- Core application logic
- API endpoints
- Data processing modules
- Machine learning models
- Database interactions

### `/tests/` - Test Suite
Comprehensive test suite including:
- Unit tests
- Integration tests
- End-to-end tests
- Test configurations and fixtures

### `/demo/` - Demonstrations
Example scripts and demonstrations:
- Feature demonstrations
- Usage examples
- Sample data processing
- Results and outputs in `/demo/results/`

### `/validation/` - Validation Scripts
Scripts for validating functionality:
- Data validation
- Model validation
- System health checks
- Environment verification

### `/docs/` - Documentation
Organized documentation:
- `/guides/` - User and developer guides
- `/implementation/` - Technical implementation details
- `/reports/` - Progress reports and project summaries

### `/scripts/` - Utility Scripts
Automation and utility scripts:
- Build scripts
- Deployment helpers
- CI/CD utilities
- Data processing scripts

### `/deployment/` - Deployment Configuration
Infrastructure and deployment files:
- Kubernetes manifests
- Terraform configurations
- Database schemas
- Environment configurations

### `/config/` - Configuration Files
Application configuration:
- Environment-specific settings
- Service configurations
- Feature flags

### `/data/` - Data Storage
Data files and datasets:
- Sample datasets
- Test data
- Generated data

### `/logs/` - Log Files
Application and system logs:
- Application logs
- Error logs
- Access logs
- System logs

## File Organization Guidelines

1. **Source Code**: All application code goes in `/src/`
2. **Tests**: All test files go in `/tests/`
3. **Documentation**: Use the appropriate subdirectory in `/docs/`
4. **Demo Scripts**: Place in `/demo/` with results in `/demo/results/`
5. **Utilities**: Shell scripts and utilities go in `/scripts/`
6. **Logs**: All log files should be written to `/logs/`

## Development Workflow

1. Source code development in `/src/`
2. Write tests in `/tests/`
3. Create demos in `/demo/`
4. Document in `/docs/`
5. Use validation scripts to verify functionality
6. Deploy using configurations in `/deployment/`

This structure ensures clean separation of concerns and makes the project easy to navigate and maintain.
