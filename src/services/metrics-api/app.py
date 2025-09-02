from fastapi import FastAPI, Query, HTTPException
from subprocess import run, PIPE, CalledProcessError
import csv
import io
import json
import os
from typing import Optional, List, Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NeuroNews Metrics API",
    description="Minimal FastAPI service to expose dbt metrics via MetricFlow",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Set dbt project paths
DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/app/dbt")
DBT_PROFILES_DIR = os.getenv("DBT_PROFILES_DIR", "/app/dbt")

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {
        "service": "NeuroNews Metrics API",
        "status": "healthy",
        "version": "1.0.0",
        "endpoints": {
            "metrics": "/metrics",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
def health_check():
    """Health check with MetricFlow validation"""
    try:
        # Test MetricFlow connection
        cmd = ["mf", "validate-configs", "--skip-dw"]
        result = run(cmd, stdout=PIPE, stderr=PIPE, text=True, check=True, cwd=DBT_PROJECT_DIR)
        return {
            "status": "healthy",
            "metricflow": "connected",
            "dbt_project": DBT_PROJECT_DIR
        }
    except CalledProcessError as e:
        logger.error(f"MetricFlow validation failed: {e.stderr}")
        return {
            "status": "unhealthy",
            "metricflow": "disconnected",
            "error": e.stderr
        }

@app.get("/metrics")
def get_metrics(
    name: str = Query(..., description="Metric name to query (e.g., articles_ingested)"),
    group_by: str = Query("metric_time__day", description="Dimension to group by (e.g., metric_time__day, source__country)"),
    limit: int = Query(200, description="Maximum number of rows to return", ge=1, le=1000),
    format: str = Query("json", description="Response format: json or csv")
) -> Dict[str, Any]:
    """
    Query dbt metrics via MetricFlow
    
    Examples:
    - /metrics?name=articles_ingested&group_by=metric_time__day&limit=10
    - /metrics?name=unique_sources&group_by=metric_time__month&limit=5
    - /metrics?name=articles_ingested&group_by=metric_time__day,source__country&limit=20
    """
    try:
        logger.info(f"Querying metric: {name}, group_by: {group_by}, limit: {limit}")
        
        # Build MetricFlow command
        cmd = [
            "mf", "query",
            "--metrics", name,
            "--group-by", group_by,
            "--limit", str(limit),
            "--format", "csv"
        ]
        
        # Execute MetricFlow query
        result = run(
            cmd, 
            stdout=PIPE, 
            stderr=PIPE, 
            text=True, 
            check=False,
            cwd=DBT_PROJECT_DIR
        )
        
        if result.returncode != 0:
            logger.error(f"MetricFlow query failed: {result.stderr}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "MetricFlow query failed",
                    "message": result.stderr,
                    "metric": name,
                    "group_by": group_by
                }
            )
        
        # Parse CSV output
        if format.lower() == "csv":
            return {
                "metric": name,
                "group_by": group_by,
                "limit": limit,
                "format": "csv",
                "data": result.stdout
            }
        
        # Parse CSV to JSON
        reader = csv.DictReader(io.StringIO(result.stdout))
        rows = list(reader)
        
        return {
            "metric": name,
            "group_by": group_by,
            "limit": limit,
            "format": "json",
            "count": len(rows),
            "data": rows
        }
        
    except Exception as e:
        logger.error(f"Unexpected error querying metric {name}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": str(e),
                "metric": name
            }
        )

@app.get("/metrics/available")
def list_available_metrics() -> Dict[str, Any]:
    """
    List all available metrics in the semantic layer
    """
    try:
        # Get list of metrics using MetricFlow
        cmd = ["mf", "list", "metrics"]
        result = run(
            cmd,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            check=True,
            cwd=DBT_PROJECT_DIR
        )
        
        # Parse the output to extract metric names
        metrics = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line and not line.startswith('─') and not line.startswith('│'):
                # Clean up the metric name
                metric_name = line.replace('│', '').strip()
                if metric_name and metric_name != 'Metrics':
                    metrics.append(metric_name)
        
        return {
            "available_metrics": metrics,
            "count": len(metrics)
        }
        
    except CalledProcessError as e:
        logger.error(f"Failed to list metrics: {e.stderr}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list available metrics",
                "message": e.stderr
            }
        )

@app.get("/dimensions")
def list_available_dimensions() -> Dict[str, Any]:
    """
    List all available dimensions for grouping
    """
    try:
        # Get list of dimensions using MetricFlow
        cmd = ["mf", "list", "dimensions"]
        result = run(
            cmd,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            check=True,
            cwd=DBT_PROJECT_DIR
        )
        
        # Parse the output to extract dimension names
        dimensions = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line and not line.startswith('─') and not line.startswith('│'):
                # Clean up the dimension name
                dimension_name = line.replace('│', '').strip()
                if dimension_name and dimension_name != 'Dimensions':
                    dimensions.append(dimension_name)
        
        return {
            "available_dimensions": dimensions,
            "count": len(dimensions)
        }
        
    except CalledProcessError as e:
        logger.error(f"Failed to list dimensions: {e.stderr}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to list available dimensions",
                "message": e.stderr
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
