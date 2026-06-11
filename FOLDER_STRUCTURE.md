# NeuroNews Folder Structure

This document describes the organized folder structure of the NeuroNews project.

## Root Directory
Contains only essential project files:
- `README.md` - Main project documentation
- `requirements.txt` - Python dependencies
- `pyproject.toml` - Python project configuration
- `Makefile` - Build and automation commands
- `LICENSE` - Project license
- `Dockerfile*` - Container definitions
- `docker-compose*.yml` - Docker orchestration files
- `appspec.yml` - AWS CodeDeploy configuration
- `.gitignore`, `.dockerignore` - Git and Docker ignore files

## Source Code (`src/`)
Main application source code organized by modules:
- API routes and endpoints
- Core business logic
- Knowledge graph services
- Data processing pipelines
- Authentication and security

## Documentation (`docs/`)
Organized documentation by category:

### `docs/implementation-reports/`
- Issue implementation summaries
- Feature completion reports
- Technical decision documents
- CI/CD implementation guides

### `docs/guides/`
- Deployment guides (AWS, Kubernetes)
- Anti-detection strategies
- Monitoring system setup
- Integration guides

## Demo Scripts (`demo/`)
Demonstration and example scripts:
- Feature demonstrations
- API usage examples
- Integration testing demos
- Performance benchmarks

## Tests (`tests/`)
Test suites and testing utilities:
- Unit tests
- Integration tests
- API endpoint tests
- Security tests
- Performance tests

## Validation (`validation/`)
Validation scripts and verification tools:
- Implementation validators
- Data integrity checks
- System health verifications
- Compliance checkers

## Scripts (`scripts/`)
Utility scripts organized by purpose:

### `scripts/ci-cd/`
- CI/CD pipeline utilities
- Package management scripts
- Integration test runners

### `scripts/utilities/`
- Code formatting tools
- Cleanup utilities
- Status checkers
- Manual fix scripts

## Infrastructure (`infrastructure/`)
Infrastructure as Code and deployment configurations:
- Terraform configurations
- CloudFormation templates
- Kubernetes manifests

## Docker (`docker/`)
Docker-related configurations:
- Service-specific Dockerfiles
- Docker Compose configurations
- Container orchestration setups

## Data (`data/`)
Data files and configurations:
- Sample datasets
- Configuration files
- Log files
- Test data
- Coverage reports

## Other Directories

### `airflow/`
Apache Airflow configurations:
- DAG definitions
- Custom operators
- Airflow plugins

### `ansible/`
Ansible playbooks and roles:
- Server provisioning
- Application deployment
- Configuration management

### `k8s/`
Kubernetes manifests:
- Deployment configurations
- Service definitions
- ConfigMaps and Secrets

### `logs/`
Application logs and runtime data

### `config/`
Application configuration files

### `htmlcov/`
HTML coverage reports

### `.github/`
GitHub-specific configurations:
- Workflow definitions
- Issue templates
- Pull request templates

## Benefits of This Structure

1. **Clear Separation**: Each type of file has its designated place
2. **Easy Navigation**: Developers can quickly find what they need
3. **Scalability**: Structure supports project growth
4. **Maintainability**: Easier to maintain and update
5. **CI/CD Friendly**: Clear paths for automation scripts
6. **Documentation**: Well-organized documentation by purpose

## Migration Notes

This folder structure was implemented to clean up the root directory that previously contained over 100 scattered files. The reorganization:
- Moved implementation reports to `docs/implementation-reports/`
- Moved guides to `docs/guides/`
- Moved demo scripts to `demo/`
- Moved validation scripts to `validation/`
- Moved utility scripts to `scripts/utilities/`
- Moved CI/CD scripts to `scripts/ci-cd/`
- Moved test files to `tests/`
- Moved data files to `data/`

The root directory now contains only essential project files, making the project much more navigable and professional.
