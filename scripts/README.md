# Airflow Bootstrap Script (Issue #194)

This directory contains the bootstrap script for setting up Airflow connections and variables for the NeuroNews project.

## Overview

The `airflow_bootstrap.sh` script automates the setup of:
- **Connections**: AWS and PostgreSQL connections for data operations
- **Variables**: Environment-specific configuration variables
- **Validation**: Ensures all components are properly configured

## Features

- ✅ **Idempotent**: Safe to run multiple times
- ✅ **Environment-aware**: Supports dev, staging, and production configurations
- ✅ **Validation**: Automatically validates all connections and variables
- ✅ **Error handling**: Comprehensive error checking and rollback
- ✅ **Documentation**: Built-in help and usage examples

## Quick Start

### Prerequisites

1. Airflow services running (use `make airflow-up`)
2. Airflow database initialized (`airflow db init`)
3. Access to Airflow webserver container

### Basic Usage

```bash
# Run inside Airflow webserver container
docker exec $(docker-compose -f docker/airflow/docker-compose.airflow.yml ps -q airflow-webserver) \
    bash -c 'cd /opt/airflow && ./scripts/airflow_bootstrap.sh'

# Or use the Makefile target
make airflow-bootstrap
```

### With Custom Configuration

```bash
# Create custom environment file
cat > custom.env << EOF
AWS_ACCESS_KEY_ID=your_actual_key
AWS_SECRET_ACCESS_KEY=your_actual_secret
AWS_DEFAULT_REGION=eu-central-1
ENVIRONMENT=production
EOF

# Run with custom environment
./scripts/airflow_bootstrap.sh --env-file custom.env --verbose
```

## Connections Created

### 1. aws_default
- **Type**: AWS
- **Purpose**: S3 access and other AWS services
- **Configuration**: Uses environment variables for credentials
- **Fallback**: Creates placeholder if credentials not provided

### 2. neuro_postgres
- **Type**: PostgreSQL
- **Purpose**: Metadata and additional database operations
- **Configuration**: Uses existing database connection details

## Variables Created

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `DATA_ROOT` | `/opt/airflow/data` | Root directory for data files |
| `NAMESPACE` | `neuro_news_dev` | OpenLineage namespace |
| `ENVIRONMENT` | `dev` | Current environment (dev/staging/prod) |
| `OPENLINEAGE_URL` | `http://marquez:5000` | Marquez server URL |
| `OPENLINEAGE_NAMESPACE` | `neuro_news_dev` | OpenLineage namespace |
| `PROJECT_VERSION` | `1.0.0` | Project version identifier |

## Environment Variables

### Required for AWS (Optional)
```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1  # default
```

### Database Configuration
```bash
POSTGRES_HOST=postgres        # default
POSTGRES_PORT=5432           # default
POSTGRES_USER=airflow        # default
POSTGRES_PASSWORD=airflow    # default
POSTGRES_DB=airflow          # default
```

### Project Configuration
```bash
ENVIRONMENT=dev              # dev/staging/prod
PROJECT_VERSION=1.0.0        # semantic version
OPENLINEAGE_URL=http://marquez:5000
OPENLINEAGE_NAMESPACE=neuro_news_dev
```

## Script Options

```bash
./scripts/airflow_bootstrap.sh [OPTIONS]

Options:
    --env-file PATH     Path to environment file (optional)
    --verbose          Enable verbose output
    -h, --help         Show this help message
```

## Usage Scenarios

### Development Environment

```bash
# Basic setup with defaults
make airflow-bootstrap

# Verify setup
make airflow-test-bootstrap
```

### Staging/Production Environment

```bash
# Create environment-specific config
cat > .env.staging << EOF
AWS_ACCESS_KEY_ID=staging_key
AWS_SECRET_ACCESS_KEY=staging_secret
AWS_DEFAULT_REGION=eu-west-1
ENVIRONMENT=staging
PROJECT_VERSION=1.2.0
OPENLINEAGE_NAMESPACE=neuro_news_staging
EOF

# Bootstrap with staging config
./scripts/airflow_bootstrap.sh --env-file .env.staging --verbose
```

### CI/CD Environment

```bash
# Set environment variables in CI
export AWS_ACCESS_KEY_ID="$CI_AWS_KEY"
export AWS_SECRET_ACCESS_KEY="$CI_AWS_SECRET"
export ENVIRONMENT="ci"

# Run bootstrap in CI container
docker exec airflow_container ./scripts/airflow_bootstrap.sh --verbose
```

## Validation and Testing

### Manual Validation

```bash
# Check connections
airflow connections list

# Check variables
airflow variables list

# Test specific connection
airflow connections test aws_default
```

### Automated Testing

```bash
# Run comprehensive test suite
make airflow-test-bootstrap

# Or run directly
python3 demo/demo_airflow_bootstrap.py
```

## Troubleshooting

### Common Issues

1. **Script not found**
   ```bash
   # Ensure you're in the correct directory
   cd /opt/airflow
   ls -la scripts/airflow_bootstrap.sh
   ```

2. **Permission denied**
   ```bash
   # Make script executable
   chmod +x scripts/airflow_bootstrap.sh
   ```

3. **Airflow CLI not available**
   ```bash
   # Run inside Airflow container
   docker exec -it $(docker-compose -f docker/airflow/docker-compose.airflow.yml ps -q airflow-webserver) bash
   ```

4. **Database not initialized**
   ```bash
   # Initialize Airflow database
   airflow db init
   ```

### Debug Mode

```bash
# Run with verbose output
./scripts/airflow_bootstrap.sh --verbose

# Check specific component
airflow connections get aws_default
airflow variables get DATA_ROOT
```

### Log Analysis

```bash
# Check Airflow logs for connection issues
docker-compose -f docker/airflow/docker-compose.airflow.yml logs airflow-webserver

# Check script execution logs
# (script outputs colored logs to help identify issues)
```

## Integration with Makefiles

The bootstrap script integrates with the project Makefile:

```bash
# Bootstrap connections and variables
make airflow-bootstrap

# Test bootstrap functionality
make airflow-test-bootstrap

# Full Airflow setup (including bootstrap)
make airflow-up && make airflow-bootstrap
```

## Security Considerations

1. **Credential Management**
   - Never commit real AWS credentials to version control
   - Use environment variables or secure secret management
   - Regularly rotate access keys

2. **Environment Isolation**
   - Use different credentials for dev/staging/prod
   - Separate OpenLineage namespaces per environment
   - Validate environment-specific configurations

3. **Access Control**
   - Restrict access to bootstrap script in production
   - Use IAM roles with minimal required permissions
   - Monitor connection usage and access patterns

## Best Practices

1. **Idempotency**: Script can be run multiple times safely
2. **Validation**: Always validate setup after running bootstrap
3. **Environment Variables**: Use `.env` files for consistent configuration
4. **Testing**: Run test suite to verify functionality
5. **Documentation**: Keep environment-specific configurations documented

## File Structure

```
scripts/
├── airflow_bootstrap.sh          # Main bootstrap script
└── README.md                     # This documentation

demo/
└── demo_airflow_bootstrap.py     # Test suite

docker/airflow/
└── .env.example                  # Environment configuration template
```

## Related Documentation

- [Airflow Connections Documentation](https://airflow.apache.org/docs/apache-airflow/stable/concepts/connections.html)
- [Airflow Variables Documentation](https://airflow.apache.org/docs/apache-airflow/stable/concepts/variables.html)
- [OpenLineage Integration Guide](../docs/openlineage_config.md)
- [NeuroNews Development Setup](../README.md)
