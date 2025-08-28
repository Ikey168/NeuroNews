# NeuroNews Metrics API

A minimal FastAPI service to expose dbt metrics via MetricFlow for demos and dashboards.

## Features

- 🚀 **Fast API**: Built with FastAPI for high performance and automatic API documentation
- 📊 **dbt Metrics**: Exposes semantic layer metrics via MetricFlow
- 🔍 **Flexible Queries**: Support for multiple group-by dimensions and limits
- 📋 **Auto Documentation**: Interactive API docs at `/docs`
- 🏥 **Health Checks**: Built-in health monitoring and MetricFlow validation

## API Endpoints

### Core Endpoints

- `GET /` - Service information and available endpoints
- `GET /health` - Health check with MetricFlow validation
- `GET /docs` - Interactive API documentation

### Metrics Endpoints

- `GET /metrics` - Query specific metrics with grouping
- `GET /metrics/available` - List all available metrics
- `GET /dimensions` - List all available dimensions

## Usage Examples

### Query Articles Ingested by Day
```bash
curl "http://localhost:8000/metrics?name=articles_ingested&group_by=metric_time__day&limit=10"
```

### Query Unique Sources by Month
```bash
curl "http://localhost:8000/metrics?name=unique_sources&group_by=metric_time__month&limit=5"
```

### Query with Multiple Dimensions
```bash
curl "http://localhost:8000/metrics?name=articles_ingested&group_by=metric_time__day,source__country&limit=20"
```

### List Available Metrics
```bash
curl "http://localhost:8000/metrics/available"
```

### List Available Dimensions
```bash
curl "http://localhost:8000/dimensions"
```

## Response Format

### Success Response
```json
{
  "metric": "articles_ingested",
  "group_by": "metric_time__day",
  "limit": 10,
  "format": "json",
  "count": 5,
  "data": [
    {
      "metric_time__day": "2025-08-01",
      "articles_ingested": 150
    },
    {
      "metric_time__day": "2025-08-02", 
      "articles_ingested": 203
    }
  ]
}
```

### Error Response
```json
{
  "detail": {
    "error": "MetricFlow query failed",
    "message": "Metric 'invalid_metric' not found",
    "metric": "invalid_metric",
    "group_by": "metric_time__day"
  }
}
```

## Installation & Setup

### Local Development

1. **Install dependencies**:
   ```bash
   cd services/metrics-api
   pip install -r requirements.txt
   ```

2. **Set environment variables**:
   ```bash
   export DBT_PROJECT_DIR=/path/to/your/dbt/project
   export DBT_PROFILES_DIR=/path/to/your/dbt/profiles
   ```

3. **Run the server**:
   ```bash
   uvicorn app:app --reload
   ```

4. **Access the API**:
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

### Docker Deployment

1. **Build the image**:
   ```bash
   docker build -t neuronews-metrics-api .
   ```

2. **Run the container**:
   ```bash
   docker run -p 8000:8000 \
     -v /path/to/dbt:/app/dbt \
     -e DBT_PROJECT_DIR=/app/dbt \
     -e DBT_PROFILES_DIR=/app/dbt \
     neuronews-metrics-api
   ```

## Configuration

### Environment Variables

- `DBT_PROJECT_DIR`: Path to dbt project directory (default: `/app/dbt`)
- `DBT_PROFILES_DIR`: Path to dbt profiles directory (default: `/app/dbt`)

### Query Parameters

- `name`: Metric name (required)
- `group_by`: Dimension to group by (default: `metric_time__day`)
- `limit`: Maximum rows to return (default: 200, max: 1000)
- `format`: Response format - `json` or `csv` (default: `json`)

## Available Metrics

Based on the NeuroNews dbt semantic layer:

- `articles_ingested` - Total number of articles ingested
- `unique_sources` - Number of unique news sources
- `avg_article_sentiment` - Average sentiment score of articles
- `articles_7d` - Rolling 7-day article count

## Available Dimensions

Common grouping dimensions:

- `metric_time__day` - Group by day
- `metric_time__week` - Group by week  
- `metric_time__month` - Group by month
- `source__country` - Group by source country
- `articles__language` - Group by article language
- `articles__sentiment` - Group by sentiment category

## Error Handling

The API provides detailed error responses for:

- Invalid metric names
- Unsupported dimensions
- MetricFlow query failures
- System configuration issues

## Performance

- Lightweight FastAPI framework
- Direct MetricFlow integration
- Configurable query limits
- Health check monitoring

## Development

### Testing

```bash
pytest tests/
```

### Code Formatting

```bash
black app.py
isort app.py
```

### Type Checking

```bash
mypy app.py
```
