# NeuroNews Airflow + OpenLineage Setup (Issue #187)

This directory contains the complete setup for running Apache Airflow with OpenLineage provider for automatic data lineage tracking in the NeuroNews project.

## 🎯 Overview

Our custom Airflow setup includes:
- **Custom Docker Image**: Extended Apache Airflow 2.8.1 with OpenLineage provider
- **Automatic Lineage Tracking**: All DAG operations tracked via OpenLineage
- **Marquez Integration**: Lineage visualization with Marquez UI
- **Production Dependencies**: All required packages for NeuroNews DAGs

## 📁 Files Structure

```
docker/airflow/
├── Dockerfile                     # Custom Airflow image with OpenLineage
├── docker-compose.airflow.yml     # Complete orchestration setup
├── marquez.yml                    # Marquez configuration
├── .env.example                   # Environment variables template
└── README.md                      # This file

../../airflow/
├── requirements.txt               # Python dependencies for Airflow
├── dags/                         # Airflow DAGs directory
│   └── test_openlineage_integration.py  # Test DAG for Issue #187
├── logs/                         # Airflow logs
└── plugins/                      # Custom Airflow plugins
```

## 🚀 Quick Start

### 1. Build Custom Image (Issue #187)
```bash
make airflow-build
```

### 2. Start Services
```bash
make airflow-up
```

### 3. Test OpenLineage Integration
```bash
make airflow-test-openlineage
```

### 4. Access UIs
- **Airflow**: http://localhost:8080 (airflow/airflow)
- **Marquez**: http://localhost:3000

## 🔧 Custom Image Features (Issue #187)

Our custom Airflow image includes:

### OpenLineage Providers
- `apache-airflow-providers-openlineage==1.4.0`
- `openlineage-airflow==1.9.0`
- `openlineage-python==1.9.0`

### NeuroNews Dependencies
- **Data Processing**: pandas, numpy, scikit-learn
- **Web Scraping**: scrapy, beautifulsoup4, newspaper3k
- **NLP/ML**: nltk, textblob
- **Cloud Integration**: boto3, apache-airflow-providers-amazon
- **Graph Database**: gremlinpython

### Configuration
- Automatic lineage tracking enabled
- Marquez integration configured
- Debug mode for development

## 📊 Lineage Tracking

### Automatic Tracking
OpenLineage automatically tracks:
- **Datasets**: Input/output data sources
- **Jobs**: Airflow tasks and DAGs
- **Runs**: Execution metadata and lineage
- **Schema**: Data structure evolution

### Manual Tracking
For custom lineage events:
```python
from openlineage.airflow import OpenLineageAdapter

# Custom lineage tracking in DAGs
adapter = OpenLineageAdapter()
adapter.emit_start_event(...)
adapter.emit_complete_event(...)
```

## 🧪 Testing

### Test DAG
The `test_openlineage_integration` DAG verifies:
- ✅ OpenLineage imports work
- ✅ Provider installation complete
- ✅ Configuration loaded correctly
- ✅ Lineage events generated

### Manual Testing
```bash
# Check OpenLineage logs
make airflow-webserver-logs | grep -i openlineage

# Trigger test DAG
docker-compose exec airflow-webserver airflow dags trigger test_openlineage_integration

# View lineage in Marquez
open http://localhost:3000
```

## 🔧 Configuration

### OpenLineage Environment Variables (Issue #188)

The following environment variables control OpenLineage behavior:

```bash
# Core OpenLineage Configuration
OPENLINEAGE_URL=http://marquez:5000           # Marquez endpoint URL
OPENLINEAGE_NAMESPACE=neuro_news_dev          # Default namespace for lineage events  
OPENLINEAGE_DISABLED=false                    # Enable/disable lineage tracking
```

### Changing Namespace Per Branch

To use different namespaces for different git branches (e.g., dev, staging, prod):

1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Set branch-specific namespace**:
   ```bash
   # For development branch
   echo "OPENLINEAGE_NAMESPACE=neuro_news_dev" >> .env
   
   # For staging branch  
   echo "OPENLINEAGE_NAMESPACE=neuro_news_staging" >> .env
   
   # For production branch
   echo "OPENLINEAGE_NAMESPACE=neuro_news_prod" >> .env
   ```

3. **Or set dynamically based on git branch**:
   ```bash
   # Get current branch name
   BRANCH_NAME=$(git branch --show-current)
   echo "OPENLINEAGE_NAMESPACE=neuro_news_${BRANCH_NAME}" >> .env
   ```

4. **Restart services to apply changes**:
   ```bash
   make airflow-down
   make airflow-up
   ```

### Airflow OpenLineage Provider Settings

The following Airflow configuration is automatically set from environment variables:

```yaml
AIRFLOW__OPENLINEAGE__TRANSPORT: '{"type": "http", "url": "${OPENLINEAGE_URL}", "endpoint": "/api/v1/lineage"}'
AIRFLOW__OPENLINEAGE__NAMESPACE: ${OPENLINEAGE_NAMESPACE}
AIRFLOW__OPENLINEAGE__DISABLED: ${OPENLINEAGE_DISABLED}
AIRFLOW__OPENLINEAGE__DEBUG: 'true'
```

### Environment Variables
Copy `.env.example` to `.env` and customize:
```bash
cp .env.example .env
```

## 📋 Makefile Commands

| Command | Description |
|---------|-------------|
| `make airflow-build` | Build custom image with OpenLineage |
| `make airflow-up` | Start all services |
| `make airflow-down` | Stop all services |
| `make airflow-test-openlineage` | Test OpenLineage integration |
| `make airflow-logs` | View all logs |
| `make airflow-status` | Check service status |
| `make marquez-ui` | Open Marquez UI |

## 🏗️ Architecture

```mermaid
graph TB
    A[Airflow DAGs] --> B[OpenLineage Provider]
    B --> C[HTTP Transport]
    C --> D[Marquez API]
    D --> E[Marquez UI]
    D --> F[PostgreSQL]
    
    G[Custom Image] --> A
    G --> H[NeuroNews Dependencies]
    G --> I[OpenLineage Packages]
```

## 🔍 Verification

### Issue #187 Requirements (Custom Image)

#### 1. Custom Image Built
```bash
docker images | grep neuronews/airflow
# Should show: neuronews/airflow:2.8.1-openlineage
```

#### 2. OpenLineage Provider Installed
```bash
docker-compose exec airflow-webserver python -c "import openlineage.airflow; print('✅ OpenLineage ready')"
```

#### 3. No Import Errors in Logs
```bash
make airflow-webserver-logs | grep -i "error\|exception" | grep -i openlineage
# Should show no critical errors
```

#### 4. Lineage Events Generated
- Run test DAG: `make airflow-test-openlineage`
- Check Marquez UI: http://localhost:3000
- Verify lineage events appear

### Issue #188 Requirements (Environment Configuration)

#### DoD: Trigger any example DAG → run appears in Marquez UI under neuro_news_dev

1. **Verify environment variables are loaded**:
   ```bash
   docker-compose exec airflow-webserver env | grep OPENLINEAGE
   # Should show:
   # OPENLINEAGE_URL=http://marquez:5000
   # OPENLINEAGE_NAMESPACE=neuro_news_dev
   # OPENLINEAGE_DISABLED=false
   ```

2. **Check Airflow configuration**:
   ```bash
   docker-compose exec airflow-webserver airflow config get-value openlineage namespace
   # Should output: neuro_news_dev
   ```

3. **Trigger test DAG and verify in Marquez**:
   ```bash
   # Start services
   make airflow-up
   
   # Trigger example DAG  
   docker-compose exec airflow-webserver airflow dags trigger test_openlineage_integration
   
   # Check Marquez UI at http://localhost:3000
   # Should see runs under "neuro_news_dev" namespace
   ```

4. **Verify namespace can be changed per branch**:
   ```bash
   # Update .env file
   echo "OPENLINEAGE_NAMESPACE=neuro_news_test" > .env
   
   # Restart services
   make airflow-down && make airflow-up
   
   # Trigger DAG again
   docker-compose exec airflow-webserver airflow dags trigger test_openlineage_integration
   
   # Check Marquez UI - should see runs under "neuro_news_test" namespace
   ```

## 🚨 Troubleshooting

### Build Issues
```bash
# Clean build
docker system prune -f
make airflow-build

# Check build logs
docker build --no-cache -t neuronews/airflow:2.8.1-openlineage docker/airflow/
```

### Runtime Issues
```bash
# Check service health
make airflow-status

# View specific logs
make airflow-webserver-logs
make marquez-logs

# Restart services
make airflow-down
make airflow-up
```

### OpenLineage Issues
```bash
# Test OpenLineage manually
docker-compose exec airflow-webserver python -c "
from openlineage.client import OpenLineageClient
from openlineage.client.transport import HttpTransport
transport = HttpTransport('http://marquez:5000')
client = OpenLineageClient(transport=transport)
print('✅ OpenLineage client works')
"
```

## 📚 Resources

- [OpenLineage Documentation](https://openlineage.io/)
- [Apache Airflow Documentation](https://airflow.apache.org/)
- [Marquez Documentation](https://marquezproject.ai/)
- [Issue #187](https://github.com/Ikey168/NeuroNews/issues/187)

---

**Status**: ✅ Issue #187 Implementation Complete
**Image**: `neuronews/airflow:2.8.1-openlineage`
**Verification**: See DoD section above
