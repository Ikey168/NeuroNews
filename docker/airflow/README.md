# Airflow + Marquez Integration

This directory contains the Docker Compose setup for running Apache Airflow with Marquez for data lineage tracking.

## Quick Start

1. **Initialize and start services:**
   ```bash
   make airflow-up
   ```

2. **Access the UIs:**
   - Airflow Web UI: http://localhost:8080 (username: `airflow`, password: `airflow`)
   - Marquez Web UI: http://localhost:3000

3. **Stop services:**
   ```bash
   make airflow-down
   ```

## Components

### Apache Airflow
- **Web Server**: http://localhost:8080
- **Scheduler**: Runs DAGs on schedule
- **Executor**: LocalExecutor (single machine)
- **Database**: PostgreSQL (metadata storage)

### Marquez (OpenLineage)
- **API Server**: http://localhost:5000
- **Web UI**: http://localhost:3000
- **Database**: PostgreSQL (lineage metadata)

## Directory Structure

```
docker/airflow/
├── docker-compose.airflow.yml  # Main compose file
├── marquez.yml                 # Marquez configuration
├── .env.example               # Environment variables template
└── README.md                  # This file

airflow/
├── dags/                      # DAG files (Python)
├── logs/                      # Airflow logs
└── plugins/                   # Custom plugins
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize as needed:

```bash
cd docker/airflow
cp .env.example .env
```

Key variables:
- `AIRFLOW_UID`: User ID for Airflow processes (default: 50000)
- `_AIRFLOW_WWW_USER_USERNAME`: Web UI username
- `_AIRFLOW_WWW_USER_PASSWORD`: Web UI password

### OpenLineage Integration

Airflow is pre-configured to send lineage metadata to Marquez:
- Transport: HTTP to `http://marquez:5000`
- Namespace: `neuronews`
- Endpoint: `/api/v1/lineage`

## Development

### Adding DAGs

Place your DAG files in `./airflow/dags/`. They will be automatically loaded by Airflow.

Example DAG with lineage:
```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator

default_args = {
    'owner': 'neuronews',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'example_dag',
    default_args=default_args,
    description='Example DAG with lineage',
    schedule_interval='@daily',
    catchup=False,
    tags=['example', 'neuronews'],
)

start = DummyOperator(
    task_id='start',
    dag=dag,
)

end = DummyOperator(
    task_id='end',
    dag=dag,
)

start >> end
```

### Logs and Debugging

View logs for specific services:
```bash
make airflow-logs                 # All services
make airflow-webserver-logs       # Web server only
make airflow-scheduler-logs       # Scheduler only
make marquez-logs                 # Marquez only
```

### Service Health

Check service status:
```bash
make airflow-status
```

## Ports

| Service | Port | Description |
|---------|------|-------------|
| Airflow Web | 8080 | Web UI and API |
| Marquez API | 5000 | REST API |
| Marquez Web | 3000 | Web UI |
| Postgres (Airflow) | 5432 | Airflow metadata DB |
| Postgres (Marquez) | 5433 | Marquez metadata DB |

## Troubleshooting

### Permission Issues
If you encounter permission errors:
```bash
sudo chown -R $USER:$USER ./airflow/
```

### Clean Reset
To completely reset the environment:
```bash
make airflow-clean
```

### Database Connection Issues
Ensure PostgreSQL services are healthy:
```bash
docker-compose -f docker-compose.airflow.yml ps
```

## Production Considerations

This setup is designed for local development. For production:

1. **Use external databases** (RDS, CloudSQL, etc.)
2. **Configure proper authentication** (LDAP, OAuth)
3. **Use CeleryExecutor** for scalability
4. **Set up monitoring** (Prometheus, Grafana)
5. **Configure SSL/TLS** for web interfaces
6. **Use secrets management** (Vault, AWS Secrets Manager)

## References

- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [Marquez Documentation](https://marquezproject.github.io/marquez/)
- [OpenLineage Specification](https://openlineage.io/)
