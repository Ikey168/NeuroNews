"""
Local Dashboard Service for News Insights.

This module implements Issue #49 (originally "Develop AWS QuickSight Dashboard
for News Insights") using a LOCAL, file-based backend instead of AWS QuickSight.

AWS QuickSight is a managed BI service with no free local equivalent, so this
module persists dashboard / dataset / analysis / data-source definitions as JSON
files on local disk. No AWS account and no boto3/botocore are required.

Key Features:
1. Set up a local dashboard backend for interactive visualization metadata
2. Create dashboard layout definitions for:
   - Trending topics by sentiment
   - Knowledge graph entity relationships
   - Event timeline analysis
3. Enable filtering by date, entity, and sentiment
4. Persist definitions so describe/list/delete operate on local files

Local store layout (under NEURONEWS_DASHBOARDS_DIR, default ./data/dashboards):
    <root>/data_sources/<id>.json
    <root>/data_sets/<id>.json
    <root>/analyses/<id>.json
    <root>/dashboards/<id>.json

Dependencies:
- stdlib only (json, os, uuid, datetime)
- src.database.snowflake_analytics_connector for data source integration
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DASHBOARDS_DIR = "./data/dashboards"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _get_dashboards_dir() -> str:
    """Return the local dashboards root directory.

    Controlled by NEURONEWS_DASHBOARDS_DIR (default ./data/dashboards).
    """
    return os.environ.get("NEURONEWS_DASHBOARDS_DIR", DEFAULT_DASHBOARDS_DIR)


class DashboardResourceNotFoundError(Exception):
    """Raised when a requested local resource definition does not exist.

    Replaces botocore's ResourceNotFoundException.
    """


class LocalResourceType(Enum):
    """Local dashboard resource types."""

    DATA_SOURCE = "data_source"
    DATA_SET = "data_set"
    ANALYSIS = "analysis"
    DASHBOARD = "dashboard"
    TEMPLATE = "template"


class DashboardType(Enum):
    """Dashboard layout types."""

    SENTIMENT_TRENDS = "sentiment_trends"
    ENTITY_RELATIONSHIPS = "entity_relationships"
    EVENT_TIMELINE = "event_timeline"
    COMPREHENSIVE = "comprehensive"


@dataclass
class LocalDashboardConfig:
    """Configuration for the local dashboard service."""

    aws_account_id: str = "local"
    region: str = "local"
    namespace: str = "default"
    data_source_id: str = "neuronews-snowflake-ds"
    data_source_name: str = "NeuroNews Snowflake Data Source"
    dashboard_prefix: str = "NeuroNews"

    # Local storage root for persisted definitions
    storage_dir: Optional[str] = None

    # Snowflake connection details (kept for dataset/data-source metadata)
    snowflake_account: Optional[str] = None
    snowflake_warehouse: str = "ANALYTICS_WH"
    snowflake_database: str = "NEURONEWS"
    snowflake_schema: str = "PUBLIC"
    snowflake_username: Optional[str] = None
    snowflake_password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "LocalDashboardConfig":
        """Create configuration from environment variables."""
        return cls(
            aws_account_id=os.getenv("AWS_ACCOUNT_ID", "local"),
            region=os.getenv("AWS_REGION", "local"),
            storage_dir=os.getenv("NEURONEWS_DASHBOARDS_DIR"),
            snowflake_account=os.getenv("SNOWFLAKE_ACCOUNT"),
            snowflake_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH"),
            snowflake_database=os.getenv("SNOWFLAKE_DATABASE", "NEURONEWS"),
            snowflake_schema=os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC"),
            snowflake_username=os.getenv("SNOWFLAKE_USER"),
            snowflake_password=os.getenv("SNOWFLAKE_PASSWORD"),
        )


@dataclass
class DashboardLayout:
    """Dashboard layout configuration."""

    name: str
    description: str
    layout_type: DashboardType
    visuals: List[Dict[str, Any]]
    filters: List[Dict[str, Any]]
    refresh_schedule: Optional[Dict[str, Any]] = None


class LocalDashboardService:
    """Service for managing local, file-based dashboards for news insights.

    This is a local replacement for the former AWS QuickSight-backed service.
    All create/describe/list/delete operations read and write JSON definition
    files under the configured storage directory; no network calls are made.
    """

    def __init__(self, config: Optional[LocalDashboardConfig] = None):
        """Initialize the local dashboard service."""
        self.config = config or LocalDashboardConfig.from_env()

        # Resolve and create the local storage root + subdirectories
        self.storage_dir = self.config.storage_dir or _get_dashboards_dir()
        self._subdirs = {
            LocalResourceType.DATA_SOURCE: os.path.join(
                self.storage_dir, "data_sources"
            ),
            LocalResourceType.DATA_SET: os.path.join(self.storage_dir, "data_sets"),
            LocalResourceType.ANALYSIS: os.path.join(self.storage_dir, "analyses"),
            LocalResourceType.DASHBOARD: os.path.join(self.storage_dir, "dashboards"),
        }
        for path in self._subdirs.values():
            os.makedirs(path, exist_ok=True)

        logger.info(
            "Local dashboard service initialized (storage_dir=%s)", self.storage_dir
        )

        # Validate configuration
        self._validate_config()

    # ------------------------------------------------------------------
    # Local store helpers (replacements for boto3 quicksight/sts clients)
    # ------------------------------------------------------------------
    def _resource_path(self, resource_type: LocalResourceType, resource_id: str) -> str:
        """Return the JSON file path for a given resource."""
        return os.path.join(self._subdirs[resource_type], f"{resource_id}.json")

    def _local_arn(self, resource_type: LocalResourceType, resource_id: str) -> str:
        """Build a synthetic local ARN-like identifier for a resource."""
        return "local:{0}:{1}:{2}".format(
            self.config.namespace, resource_type.value, resource_id
        )

    def _write_resource(
        self,
        resource_type: LocalResourceType,
        resource_id: str,
        definition: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist a resource definition to disk and return its stored record."""
        path = self._resource_path(resource_type, resource_id)
        existing_created = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_created = json.load(f).get("created_time")
            except (OSError, ValueError):
                existing_created = None

        now = _now_iso()
        record = {
            "id": resource_id,
            "resource_type": resource_type.value,
            "arn": self._local_arn(resource_type, resource_id),
            "uuid": str(uuid.uuid4()),
            "created_time": existing_created or now,
            "last_updated_time": now,
            "definition": definition,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str)
        return record

    def _read_resource(
        self, resource_type: LocalResourceType, resource_id: str
    ) -> Dict[str, Any]:
        """Read a resource definition from disk.

        Raises DashboardResourceNotFoundError if it does not exist.
        """
        path = self._resource_path(resource_type, resource_id)
        if not os.path.exists(path):
            raise DashboardResourceNotFoundError(
                "{0} '{1}' not found".format(resource_type.value, resource_id)
            )
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resource_exists(
        self, resource_type: LocalResourceType, resource_id: str
    ) -> bool:
        """Return True if a resource definition file exists."""
        return os.path.exists(self._resource_path(resource_type, resource_id))

    def _list_resources(
        self, resource_type: LocalResourceType
    ) -> List[Dict[str, Any]]:
        """List all persisted resources of a given type."""
        directory = self._subdirs[resource_type]
        records: List[Dict[str, Any]] = []
        if not os.path.isdir(directory):
            return records
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except (OSError, ValueError):
                continue
        return records

    def _delete_resource(
        self, resource_type: LocalResourceType, resource_id: str
    ) -> bool:
        """Delete a persisted resource. Returns True if a file was removed."""
        path = self._resource_path(resource_type, resource_id)
        if not os.path.exists(path):
            raise DashboardResourceNotFoundError(
                "{0} '{1}' not found".format(resource_type.value, resource_id)
            )
        os.remove(path)
        return True

    def _validate_config(self) -> None:
        """Validate dashboard configuration."""
        required_fields = ["snowflake_account", "snowflake_username"]
        missing_fields = [
            field for field in required_fields if not getattr(self.config, field)
        ]

        if missing_fields:
            logger.warning(
                "Missing configuration fields: {0}".format(missing_fields))
            logger.info(
                "Some functionality may be limited without full configuration")

    async def setup_dashboard_resources(self) -> Dict[str, Any]:
        """
        Set up the local dashboard backend for interactive visualization.

        This implements the first requirement of Issue #49.
        """
        logger.info("Setting up local dashboard resources...")

        setup_results = {
            "data_source_created": False,
            "datasets_created": [],
            "analyses_created": [],
            "dashboards_created": [],
            "errors": [],
        }
        try:
            # 1. Create Snowflake data source definition
            data_source_result = await self._create_snowflake_data_source()
            setup_results["data_source_created"] = data_source_result["success"]

            if not data_source_result["success"]:
                setup_results["errors"].append(
                    f"Data source creation failed: {data_source_result.get('error')}"
                )
                return setup_results

            # 2. Create datasets for different views
            datasets = await self._create_datasets()
            setup_results["datasets_created"] = [
                ds["name"] for ds in datasets if ds["success"]
            ]

            # 3. Create analyses for different dashboard types
            analyses = await self._create_analyses()
            setup_results["analyses_created"] = [
                a["name"] for a in analyses if a["success"]
            ]

            # 4. Create dashboards
            dashboards = await self._create_dashboards()
            setup_results["dashboards_created"] = [
                d["name"] for d in dashboards if d["success"]
            ]

            logger.info("Local dashboard setup completed successfully")
            return setup_results

        except Exception as e:
            logger.error(
                "Failed to set up local dashboard resources: {0}".format(e))
            setup_results["errors"].append(str(e))
            return setup_results

    async def _create_snowflake_data_source(self) -> Dict[str, Any]:
        """Create (persist) a Snowflake data source definition."""
        try:
            data_source_id = self.config.data_source_id
            definition = {
                "DataSourceId": data_source_id,
                "Name": self.config.data_source_name,
                "Type": "SNOWFLAKE",
                "DataSourceParameters": {
                    "SnowflakeParameters": {
                        "Host": self.config.snowflake_account,
                        "Database": self.config.snowflake_database,
                        "Warehouse": self.config.snowflake_warehouse,
                    }
                },
                "SslProperties": {"DisableSsl": False},
            }

            # Check if data source already exists
            if self._resource_exists(LocalResourceType.DATA_SOURCE, data_source_id):
                logger.info("Snowflake data source already exists")
                return {
                    "success": True,
                    "action": "already_exists",
                    "data_source_id": data_source_id,
                }

            # Create new data source definition
            record = self._write_resource(
                LocalResourceType.DATA_SOURCE, data_source_id, definition
            )

            logger.info("Created Snowflake data source: {0}".format(data_source_id))
            return {
                "success": True,
                "action": "created",
                "data_source_id": data_source_id,
                "arn": record["arn"],
            }

        except Exception as e:
            logger.error(
                "Failed to create Snowflake data source: {0}".format(e))
            return {"success": False, "error": str(e)}

    async def _create_datasets(self) -> List[Dict[str, Any]]:
        """Create (persist) dataset definitions for different dashboard views."""
        datasets_to_create = [
            {
                "id": "sentiment_trends_dataset",
                "name": "NeuroNews Sentiment Trends",
                "sql": self._get_sentiment_trends_sql(),
                "description": "Dataset for trending topics by sentiment analysis",
            },
            {
                "id": "entity_relationships_dataset",
                "name": "NeuroNews Entity Relationships",
                "sql": self._get_entity_relationships_sql(),
                "description": "Dataset for knowledge graph entity relationships",
            },
            {
                "id": "event_timeline_dataset",
                "name": "NeuroNews Event Timeline",
                "sql": self._get_event_timeline_sql(),
                "description": "Dataset for event timeline analysis",
            },
        ]

        results = []

        for dataset_config in datasets_to_create:
            try:
                dataset_id = dataset_config["id"]

                # Check if dataset already exists
                if self._resource_exists(LocalResourceType.DATA_SET, dataset_id):
                    logger.info("Dataset {0} already exists".format(dataset_id))
                    results.append(
                        {
                            "success": True,
                            "action": "already_exists",
                            "name": dataset_config["name"],
                            "id": dataset_id,
                        }
                    )
                    continue

                # Create dataset definition
                definition = {
                    "DataSetId": dataset_id,
                    "Name": dataset_config["name"],
                    "Description": dataset_config["description"],
                    "PhysicalTableMap": {
                        "CustomSql": {
                            "DataSourceArn": self._local_arn(
                                LocalResourceType.DATA_SOURCE,
                                self.config.data_source_id,
                            ),
                            "Name": dataset_config["name"],
                            "SqlQuery": dataset_config["sql"],
                            "Columns": self._get_dataset_columns(dataset_config["id"]),
                        },
                    },
                    "ImportMode": "DIRECT_QUERY",
                }
                record = self._write_resource(
                    LocalResourceType.DATA_SET, dataset_id, definition
                )

                logger.info("Created dataset: {0}".format(dataset_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": dataset_config["name"],
                        "id": dataset_id,
                        "arn": record["arn"],
                    }
                )

            except Exception as e:
                logger.error(
                    "Failed to create dataset {0}: {1}".format(dataset_config["id"], e)
                )
                results.append(
                    {
                        "success": False,
                        "action": "failed",
                        "name": dataset_config["name"],
                        "error": str(e),
                    }
                )

        return results

    def _get_sentiment_trends_sql(self) -> str:
        """SQL query for sentiment trends dataset."""
        return """
        SELECT
            DATE_TRUNC('day', published_date) as date,
            category,
            sentiment_label,
            sentiment_score,
            COUNT(*) as article_count,
            AVG(sentiment_score) as avg_sentiment,
            STRING_AGG(DISTINCT SPLIT_PART(entities, ',', 1), ', ') as top_entities,
            COUNT(DISTINCT source) as source_count
        FROM news_articles
        WHERE published_date >= CURRENT_DATE - INTERVAL '90 days'
            AND sentiment_label IS NOT NULL
        GROUP BY 1, 2, 3, 4
        ORDER BY date DESC, article_count DESC
        """

    def _get_entity_relationships_sql(self) -> str:
        """SQL query for entity relationships dataset."""
        return """
        WITH entity_pairs AS (
            SELECT
                TRIM(e1.value) as entity_1,
                TRIM(e2.value) as entity_2,
                na.category,
                na.sentiment_label,
                COUNT(*) as co_occurrence_count,
                AVG(na.sentiment_score) as avg_sentiment,
                MIN(na.published_date) as first_seen,
                MAX(na.published_date) as last_seen
            FROM news_articles na
            CROSS JOIN JSON_ARRAY_ELEMENTS_TEXT(na.entities::json) e1(value)
            CROSS JOIN JSON_ARRAY_ELEMENTS_TEXT(na.entities::json) e2(value)
            WHERE na.entities IS NOT NULL
                AND na.published_date >= CURRENT_DATE - INTERVAL '30 days'
                AND TRIM(e1.value) != TRIM(e2.value)
                AND LENGTH(TRIM(e1.value)) > 2
                AND LENGTH(TRIM(e2.value)) > 2
            GROUP BY 1, 2, 3, 4
            HAVING COUNT(*) >= 2
        )
        SELECT
            entity_1,
            entity_2,
            category,
            sentiment_label,
            co_occurrence_count,
            avg_sentiment,
            first_seen,
            last_seen,
            DATEDIFF(day, first_seen, last_seen) as relationship_duration
        FROM entity_pairs
        ORDER BY co_occurrence_count DESC, avg_sentiment DESC
        LIMIT 1000
        """

    def _get_event_timeline_sql(self) -> str:
        """SQL query for event timeline dataset."""
        return """
        SELECT
            id as article_id,
            title,
            url,
            source,
            published_date,
            category,
            sentiment_label,
            sentiment_score,
            entities,
            word_count,
            CASE
                WHEN sentiment_score >= 0.6 THEN 'High Positive'
                WHEN sentiment_score >= 0.2 THEN 'Positive'
                WHEN sentiment_score >= -0.2 THEN 'Neutral'
                WHEN sentiment_score >= -0.6 THEN 'Negative'
                ELSE 'High Negative'
            END as sentiment_category,
            CASE
                WHEN word_count >= 1000 THEN 'Long'
                WHEN word_count >= 500 THEN 'Medium'
                ELSE 'Short'
            END as article_length_category,
            EXTRACT(hour FROM published_date) as publish_hour,
            EXTRACT(dow FROM published_date) as publish_day_of_week
        FROM news_articles
        WHERE published_date >= CURRENT_DATE - INTERVAL '30 days'
            AND title IS NOT NULL
            AND content IS NOT NULL
        ORDER BY published_date DESC
        """

    def _get_dataset_columns(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Get column definitions for datasets."""
        if dataset_id == "sentiment_trends_dataset":
            return [
                {"Name": "date", "Type": "DATETIME"},
                {"Name": "category", "Type": "STRING"},
                {"Name": "sentiment_label", "Type": "STRING"},
                {"Name": "sentiment_score", "Type": "DECIMAL"},
                {"Name": "article_count", "Type": "INTEGER"},
                {"Name": "avg_sentiment", "Type": "DECIMAL"},
                {"Name": "top_entities", "Type": "STRING"},
                {"Name": "source_count", "Type": "INTEGER"},
            ]
        elif dataset_id == "entity_relationships_dataset":
            return [
                {"Name": "entity_1", "Type": "STRING"},
                {"Name": "entity_2", "Type": "STRING"},
                {"Name": "category", "Type": "STRING"},
                {"Name": "sentiment_label", "Type": "STRING"},
                {"Name": "co_occurrence_count", "Type": "INTEGER"},
                {"Name": "avg_sentiment", "Type": "DECIMAL"},
                {"Name": "first_seen", "Type": "DATETIME"},
                {"Name": "last_seen", "Type": "DATETIME"},
                {"Name": "relationship_duration", "Type": "INTEGER"},
            ]
        elif dataset_id == "event_timeline_dataset":
            return [
                {"Name": "article_id", "Type": "STRING"},
                {"Name": "title", "Type": "STRING"},
                {"Name": "url", "Type": "STRING"},
                {"Name": "source", "Type": "STRING"},
                {"Name": "published_date", "Type": "DATETIME"},
                {"Name": "category", "Type": "STRING"},
                {"Name": "sentiment_label", "Type": "STRING"},
                {"Name": "sentiment_score", "Type": "DECIMAL"},
                {"Name": "entities", "Type": "STRING"},
                {"Name": "word_count", "Type": "INTEGER"},
                {"Name": "sentiment_category", "Type": "STRING"},
                {"Name": "article_length_category", "Type": "STRING"},
                {"Name": "publish_hour", "Type": "INTEGER"},
                {"Name": "publish_day_of_week", "Type": "INTEGER"},
            ]
        else:
            return []

    async def _create_analyses(self) -> List[Dict[str, Any]]:
        """Create (persist) analysis definitions for different dashboard types."""
        analyses_to_create = [
            {
                "id": "sentiment_trends_analysis",
                "name": "NeuroNews Sentiment Trends Analysis",
                "dataset_id": "sentiment_trends_dataset",
                "description": "Analysis for trending topics by sentiment",
            },
            {
                "id": "entity_relationships_analysis",
                "name": "NeuroNews Entity Relationships Analysis",
                "dataset_id": "entity_relationships_dataset",
                "description": "Analysis for knowledge graph entity relationships",
            },
            {
                "id": "event_timeline_analysis",
                "name": "NeuroNews Event Timeline Analysis",
                "dataset_id": "event_timeline_dataset",
                "description": "Analysis for event timeline visualization",
            },
        ]

        results = []

        for analysis_config in analyses_to_create:
            try:
                analysis_id = analysis_config["id"]

                # Check if analysis already exists
                if self._resource_exists(LocalResourceType.ANALYSIS, analysis_id):
                    logger.info("Analysis {0} already exists".format(analysis_id))
                    results.append(
                        {
                            "success": True,
                            "action": "already_exists",
                            "name": analysis_config["name"],
                            "id": analysis_id,
                        }
                    )
                    continue

                # Create analysis with basic definition
                definition = {
                    "AnalysisId": analysis_id,
                    "Name": analysis_config["name"],
                    "Description": analysis_config["description"],
                    "Definition": self._get_analysis_definition(analysis_config),
                }
                record = self._write_resource(
                    LocalResourceType.ANALYSIS, analysis_id, definition
                )

                logger.info("Created analysis: {0}".format(analysis_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": analysis_config["name"],
                        "id": analysis_id,
                        "arn": record["arn"],
                    }
                )

            except Exception as e:
                logger.error(
                    "Failed to create analysis {0}: {1}".format(analysis_config["id"], e)
                )
                results.append(
                    {
                        "success": False,
                        "action": "failed",
                        "name": analysis_config["name"],
                        "error": str(e),
                    }
                )

        return results

    def _get_analysis_definition(
        self, analysis_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get analysis definition based on type."""
        dataset_id = analysis_config["dataset_id"]

        return {
            "DataSetIdentifierDeclarations": [
                {
                    "DataSetArn": self._local_arn(
                        LocalResourceType.DATA_SET, dataset_id
                    ),
                    "Identifier": dataset_id,
                }
            ],
            "Sheets": [
                {
                    "SheetId": "{0}_sheet_1".format(analysis_config["id"]),
                    "Name": "Sheet 1",
                    "Visuals": self._get_sheet_visuals(
                        analysis_config["id"], dataset_id
                    ),
                }
            ],
        }

    def _get_sheet_visuals(
        self, analysis_id: str, dataset_id: str
    ) -> List[Dict[str, Any]]:
        """Get visual definitions for analysis sheets."""
        if "sentiment_trends" in analysis_id:
            return self._get_sentiment_trends_visuals(dataset_id)
        elif "entity_relationships" in analysis_id:
            return self._get_entity_relationships_visuals(dataset_id)
        elif "event_timeline" in analysis_id:
            return self._get_event_timeline_visuals(dataset_id)
        else:
            return []

    def _get_sentiment_trends_visuals(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Get visuals for sentiment trends analysis."""
        return [
            {
                "VisualId": "sentiment_over_time",
                "LineChartVisual": {
                    "VisualId": "sentiment_over_time",
                    "Title": {
                        "Visibility": "VISIBLE",
                        "FormatText": {"PlainText": "Sentiment Trends Over Time"},
                    },
                    "FieldWells": {
                        "LineChartAggregatedFieldWells": {
                            "Category": [
                                {
                                    "DateDimensionField": {
                                        "FieldId": "date",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "date",
                                        },
                                    }
                                }
                            ],
                            "Values": [
                                {
                                    "NumericalMeasureField": {
                                        "FieldId": "avg_sentiment",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "avg_sentiment",
                                        },
                                    }
                                }
                            ],
                            "Colors": [
                                {
                                    "CategoricalDimensionField": {
                                        "FieldId": "sentiment_label",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "sentiment_label",
                                        },
                                    }
                                }
                            ],
                        }
                    },
                },
            }
        ]

    def _get_entity_relationships_visuals(
        self, dataset_id: str
    ) -> List[Dict[str, Any]]:
        """Get visuals for entity relationships analysis."""
        return [
            {
                "VisualId": "entity_network",
                "ScatterPlotVisual": {
                    "VisualId": "entity_network",
                    "Title": {
                        "Visibility": "VISIBLE",
                        "FormatText": {"PlainText": "Entity Relationship Network"},
                    },
                    "FieldWells": {
                        "ScatterPlotCategoricallyAggregatedFieldWells": {
                            "XAxis": [
                                {
                                    "CategoricalDimensionField": {
                                        "FieldId": "entity_1",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "entity_1",
                                        },
                                    }
                                }
                            ],
                            "YAxis": [
                                {
                                    "CategoricalDimensionField": {
                                        "FieldId": "entity_2",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "entity_2",
                                        },
                                    }
                                }
                            ],
                            "Size": [
                                {
                                    "NumericalMeasureField": {
                                        "FieldId": "co_occurrence_count",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "co_occurrence_count",
                                        },
                                    }
                                }
                            ],
                        }
                    },
                },
            }
        ]

    def _get_event_timeline_visuals(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Get visuals for event timeline analysis."""
        return [
            {
                "VisualId": "event_timeline",
                "LineChartVisual": {
                    "VisualId": "event_timeline",
                    "Title": {
                        "Visibility": "VISIBLE",
                        "FormatText": {"PlainText": "Event Timeline Analysis"},
                    },
                    "FieldWells": {
                        "LineChartAggregatedFieldWells": {
                            "Category": [
                                {
                                    "DateDimensionField": {
                                        "FieldId": "published_date",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "published_date",
                                        },
                                    }
                                }
                            ],
                            "Values": [
                                {
                                    "NumericalMeasureField": {
                                        "FieldId": "article_count",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "article_id",
                                        },
                                        "AggregationFunction": {
                                            "SimpleNumericalAggregation": "COUNT"
                                        },
                                    }
                                }
                            ],
                            "Colors": [
                                {
                                    "CategoricalDimensionField": {
                                        "FieldId": "sentiment_category",
                                        "Column": {
                                            "DataSetIdentifier": dataset_id,
                                            "ColumnName": "sentiment_category",
                                        },
                                    }
                                }
                            ],
                        }
                    },
                },
            }
        ]

    async def _create_dashboards(self) -> List[Dict[str, Any]]:
        """Create (persist) dashboard definitions from analyses."""
        dashboards_to_create = [
            {
                "id": "neuronews_comprehensive_dashboard",
                "name": "NeuroNews Comprehensive Dashboard",
                "description": "Complete news insights dashboard with all visualizations",
                "analysis_ids": [
                    "sentiment_trends_analysis",
                    "entity_relationships_analysis",
                    "event_timeline_analysis",
                ],
            }
        ]

        results = []

        for dashboard_config in dashboards_to_create:
            try:
                dashboard_id = dashboard_config["id"]

                # Check if dashboard already exists
                if self._resource_exists(LocalResourceType.DASHBOARD, dashboard_id):
                    logger.info("Dashboard {0} already exists".format(dashboard_id))
                    results.append(
                        {
                            "success": True,
                            "action": "already_exists",
                            "name": dashboard_config["name"],
                            "id": dashboard_id,
                        }
                    )
                    continue

                # Create dashboard definition from analyses
                definition = {
                    "DashboardId": dashboard_id,
                    "Name": dashboard_config["name"],
                    "Description": dashboard_config["description"],
                    "AnalysisIds": dashboard_config["analysis_ids"],
                    "Definition": self._get_dashboard_definition(dashboard_config),
                }
                record = self._write_resource(
                    LocalResourceType.DASHBOARD, dashboard_id, definition
                )

                logger.info("Created dashboard: {0}".format(dashboard_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": dashboard_config["name"],
                        "id": dashboard_id,
                        "arn": record["arn"],
                    }
                )

            except Exception as e:
                logger.error(
                    "Failed to create dashboard {0}: {1}".format(dashboard_config["id"], e)
                )
                results.append(
                    {
                        "success": False,
                        "name": dashboard_config["name"],
                        "id": dashboard_config["id"],
                        "error": str(e),
                    }
                )

        return results

    def _get_dashboard_definition(
        self, dashboard_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get dashboard definition combining multiple analyses."""
        return {
            "DataSetIdentifierDeclarations": [
                {
                    "DataSetArn": self._local_arn(
                        LocalResourceType.DATA_SET, "sentiment_trends_dataset"
                    ),
                    "Identifier": "sentiment_trends_dataset",
                },
                {
                    "DataSetArn": self._local_arn(
                        LocalResourceType.DATA_SET, "entity_relationships_dataset"
                    ),
                    "Identifier": "entity_relationships_dataset",
                },
                {
                    "DataSetArn": self._local_arn(
                        LocalResourceType.DATA_SET, "event_timeline_dataset"
                    ),
                    "Identifier": "event_timeline_dataset",
                },
            ],
            "Sheets": [
                {
                    "SheetId": "comprehensive_sheet",
                    "Name": "News Insights Overview",
                    "Visuals": [
                        *self._get_sentiment_trends_visuals("sentiment_trends_dataset"),
                        *self._get_entity_relationships_visuals(
                            "entity_relationships_dataset"
                        ),
                        *self._get_event_timeline_visuals("event_timeline_dataset"),
                    ],
                    "FilterControls": self._get_dashboard_filters(),
                }
            ],
        }

    def _get_dashboard_filters(self) -> List[Dict[str, Any]]:
        """
        Enable filtering by date, entity, and sentiment.

        This implements the third requirement of Issue #49.
        """
        return [
            {
                "FilterId": "date_filter",
                "DateTimePickerFilter": {
                    "FilterId": "date_filter",
                    "Title": "Date Range",
                    "Column": {
                        "DataSetIdentifier": "event_timeline_dataset",
                        "ColumnName": "published_date",
                    },
                },
            },
            {
                "FilterId": "sentiment_filter",
                "CategoryFilter": {
                    "FilterId": "sentiment_filter",
                    "Title": "Sentiment",
                    "Column": {
                        "DataSetIdentifier": "sentiment_trends_dataset",
                        "ColumnName": "sentiment_label",
                    },
                },
            },
            {
                "FilterId": "category_filter",
                "CategoryFilter": {
                    "FilterId": "category_filter",
                    "Title": "Category",
                    "Column": {
                        "DataSetIdentifier": "event_timeline_dataset",
                        "ColumnName": "category",
                    },
                },
            },
        ]

    async def create_dashboard_layout(
        self, layout_type: DashboardType
    ) -> Dict[str, Any]:
        """
        Create dashboard layout for specific insights.

        This implements the second requirement of Issue #49:
        "Create a dashboard layout for trending topics by sentiment,"
        knowledge graph entity relationships, event timeline analysis."
        """
        logger.info("Creating dashboard layout for {0}".format(
            layout_type.value))

        try:
            layout_config = self._get_layout_config(layout_type)

            # Create specific dashboard for this layout
            dashboard_id = "neuronews_{0}_dashboard".format(layout_type.value)

            definition = {
                "DashboardId": dashboard_id,
                "Name": layout_config.name,
                "Definition": {
                    "DataSetIdentifierDeclarations": [
                        {
                            "DataSetArn": self._local_arn(
                                LocalResourceType.DATA_SET,
                                self._get_dataset_for_layout(layout_type),
                            ),
                            "Identifier": self._get_dataset_for_layout(layout_type),
                        }
                    ],
                    "Sheets": [
                        {
                            "SheetId": "{0}_sheet".format(layout_type.value),
                            "Name": layout_config.name,
                            "Visuals": layout_config.visuals,
                            "FilterControls": layout_config.filters,
                        }
                    ],
                },
            }
            record = self._write_resource(
                LocalResourceType.DASHBOARD, dashboard_id, definition
            )

            logger.info("Created {0} dashboard successfully".format(
                layout_type.value))
            return {
                "success": True,
                "dashboard_id": dashboard_id,
                "dashboard_url": self._get_dashboard_url(dashboard_id),
                "arn": record["arn"],
            }

        except Exception as e:
            logger.error(
                "Failed to create dashboard layout {0}: {1}".format(
                    layout_type.value, e
                )
            )
            return {"success": False, "error": str(e)}

    def _get_layout_config(self, layout_type: DashboardType) -> DashboardLayout:
        """Get configuration for specific dashboard layout."""
        if layout_type == DashboardType.SENTIMENT_TRENDS:
            return DashboardLayout(
                name="Trending Topics by Sentiment",
                description="Dashboard showing sentiment trends across topics and time",
                layout_type=layout_type,
                visuals=self._get_sentiment_trends_visuals(
                    "sentiment_trends_dataset"),
                filters=[
                    {
                        "FilterId": "date_filter",
                        "DateTimePickerFilter": {
                            "FilterId": "date_filter",
                            "Title": "Date Range",
                            "Column": {
                                "DataSetIdentifier": "sentiment_trends_dataset",
                                "ColumnName": "date",
                            },
                        },
                    },
                    {
                        "FilterId": "sentiment_filter",
                        "CategoryFilter": {
                            "FilterId": "sentiment_filter",
                            "Title": "Sentiment",
                            "Column": {
                                "DataSetIdentifier": "sentiment_trends_dataset",
                                "ColumnName": "sentiment_label",
                            },
                        },
                    },
                ],
            )
        elif layout_type == DashboardType.ENTITY_RELATIONSHIPS:
            return DashboardLayout(
                name="Knowledge Graph Entity Relationships",
                description="Dashboard showing entity relationships and co-occurrences",
                layout_type=layout_type,
                visuals=self._get_entity_relationships_visuals(
                    "entity_relationships_dataset"
                ),
                filters=[
                    {
                        "FilterId": "entity_filter",
                        "CategoryFilter": {
                            "FilterId": "entity_filter",
                            "Title": "Entity",
                            "Column": {
                                "DataSetIdentifier": "entity_relationships_dataset",
                                "ColumnName": "entity_1",
                            },
                        },
                    },
                ],
            )
        elif layout_type == DashboardType.EVENT_TIMELINE:
            return DashboardLayout(
                name="Event Timeline Analysis",
                description="Dashboard showing event patterns and timeline analysis",
                layout_type=layout_type,
                visuals=self._get_event_timeline_visuals(
                    "event_timeline_dataset"),
                filters=[
                    {
                        "FilterId": "date_filter",
                        "DateTimePickerFilter": {
                            "FilterId": "date_filter",
                            "Title": "Date Range",
                            "Column": {
                                "DataSetIdentifier": "event_timeline_dataset",
                                "ColumnName": "published_date",
                            },
                        },
                    },
                ],
            )
        else:
            raise ValueError(
                "Unsupported layout type: {0}".format(layout_type))

    def _get_dataset_for_layout(self, layout_type: DashboardType) -> str:
        """Get dataset ID for specific layout type."""
        if layout_type == DashboardType.SENTIMENT_TRENDS:
            return "sentiment_trends_dataset"
        elif layout_type == DashboardType.ENTITY_RELATIONSHIPS:
            return "entity_relationships_dataset"
        elif layout_type == DashboardType.EVENT_TIMELINE:
            return "event_timeline_dataset"
        else:
            return "sentiment_trends_dataset"

    async def setup_real_time_updates(self) -> Dict[str, Any]:
        """
        Configure (local) refresh schedules for datasets.

        This implements the fourth requirement of Issue #49. With the local
        backend there is no managed ingestion, so refresh metadata is simply
        recorded on each dataset definition.
        """
        logger.info("Setting up local refresh schedules...")

        try:
            refresh_results = []

            datasets = [
                "sentiment_trends_dataset",
                "entity_relationships_dataset",
                "event_timeline_dataset",
            ]

            for dataset_id in datasets:
                try:
                    # Record refresh metadata on the dataset definition if present
                    if self._resource_exists(
                        LocalResourceType.DATA_SET, dataset_id
                    ):
                        record = self._read_resource(
                            LocalResourceType.DATA_SET, dataset_id
                        )
                        definition = record.get("definition", {})
                        definition["RefreshSchedule"] = {
                            "Interval": "HOURLY",
                            "RefreshType": "INCREMENTAL_REFRESH",
                            "ConfiguredAt": _now_iso(),
                        }
                        self._write_resource(
                            LocalResourceType.DATA_SET, dataset_id, definition
                        )

                    refresh_results.append(
                        {
                            "dataset_id": dataset_id,
                            "refresh_schedule": "hourly",
                            "status": "configured",
                        }
                    )

                except Exception as e:
                    logger.error(
                        "Failed to set up refresh for {0}: {1}".format(
                            dataset_id, e)
                    )
                    refresh_results.append(
                        {"dataset_id": dataset_id,
                            "status": "failed", "error": str(e)}
                    )

            logger.info("Local refresh schedule setup completed")
            return {
                "success": True,
                "refresh_schedules": refresh_results,
                "update_frequency": "hourly",
            }

        except Exception as e:
            logger.error("Failed to setup real-time updates: {0}".format(e))
            return {"success": False, "error": str(e)}

    def _get_dashboard_url(self, dashboard_id: str) -> str:
        """Get the local dashboard reference (file path URI)."""
        path = os.path.abspath(
            self._resource_path(LocalResourceType.DASHBOARD, dashboard_id)
        )
        return "file://{0}".format(path)

    async def get_dashboard_info(
        self, dashboard_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get information about created (local) dashboards."""
        try:
            if dashboard_id:
                # Get specific dashboard info
                record = self._read_resource(
                    LocalResourceType.DASHBOARD, dashboard_id
                )
                definition = record.get("definition", {})
                return {
                    "success": True,
                    "dashboard": {
                        "id": dashboard_id,
                        "name": definition.get("Name", dashboard_id),
                        "status": "CREATION_SUCCESSFUL",
                        "url": self._get_dashboard_url(dashboard_id),
                        "last_updated": record.get("last_updated_time"),
                        "created_time": record.get("created_time"),
                    },
                }
            else:
                # List all NeuroNews dashboards
                records = self._list_resources(LocalResourceType.DASHBOARD)
                neuronews_dashboards = [
                    {
                        "id": record["id"],
                        "name": record.get("definition", {}).get(
                            "Name", record["id"]
                        ),
                        "url": self._get_dashboard_url(record["id"]),
                        "last_updated": record.get("last_updated_time"),
                        "created_time": record.get("created_time"),
                    }
                    for record in records
                    if "neuronews" in record["id"].lower()
                ]

                return {
                    "success": True,
                    "dashboards": neuronews_dashboards,
                    "total_count": len(neuronews_dashboards),
                }

        except DashboardResourceNotFoundError as e:
            logger.error("Failed to get dashboard info: {0}".format(e))
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("Failed to get dashboard info: {0}".format(e))
            return {"success": False, "error": str(e)}

    async def delete_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """Delete a local dashboard definition by id."""
        try:
            self._delete_resource(LocalResourceType.DASHBOARD, dashboard_id)
            logger.info("Deleted dashboard: {0}".format(dashboard_id))
            return {"success": True, "dashboard_id": dashboard_id}
        except DashboardResourceNotFoundError as e:
            logger.warning("Dashboard not found for deletion: {0}".format(e))
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("Failed to delete dashboard: {0}".format(e))
            return {"success": False, "error": str(e)}

    async def validate_setup(self) -> Dict[str, Any]:
        """Validate local dashboard setup and resources."""
        logger.info("Validating local dashboard setup...")

        validation_results = {
            "data_source_valid": False,
            "datasets_valid": [],
            "analyses_valid": [],
            "dashboards_valid": [],
            "errors": [],
        }

        try:
            # Validate data source
            if self._resource_exists(
                LocalResourceType.DATA_SOURCE, self.config.data_source_id
            ):
                validation_results["data_source_valid"] = True
            else:
                validation_results["errors"].append(
                    "Data source validation failed: {0} not found".format(
                        self.config.data_source_id
                    )
                )

            # Validate datasets
            datasets = [
                "sentiment_trends_dataset",
                "entity_relationships_dataset",
                "event_timeline_dataset",
            ]
            for dataset_id in datasets:
                if self._resource_exists(LocalResourceType.DATA_SET, dataset_id):
                    validation_results["datasets_valid"].append(dataset_id)
                else:
                    validation_results["errors"].append(
                        "Dataset {0} validation failed: not found".format(dataset_id)
                    )

            # Validate analyses
            analyses = [
                "sentiment_trends_analysis",
                "entity_relationships_analysis",
                "event_timeline_analysis",
            ]
            for analysis_id in analyses:
                if self._resource_exists(LocalResourceType.ANALYSIS, analysis_id):
                    validation_results["analyses_valid"].append(analysis_id)
                else:
                    validation_results["errors"].append(
                        "Analysis {0} validation failed: not found".format(analysis_id)
                    )

            # Validate dashboards
            dashboards = ["neuronews_comprehensive_dashboard"]
            for dashboard_id in dashboards:
                if self._resource_exists(LocalResourceType.DASHBOARD, dashboard_id):
                    validation_results["dashboards_valid"].append(dashboard_id)
                else:
                    validation_results["errors"].append(
                        "Dashboard {0} validation failed: not found".format(
                            dashboard_id
                        )
                    )

            validation_results["overall_valid"] = (
                validation_results["data_source_valid"]
                and len(validation_results["datasets_valid"]) >= 2
                and len(validation_results["dashboards_valid"]) >= 1
            )

            logger.info(
                "Validation completed: {0}".format(
                    "Success"
                    if validation_results["overall_valid"]
                    else "Issues found"
                )
            )
            return validation_results

        except Exception as e:
            logger.error("Validation failed: {0}".format(e))
            validation_results["errors"].append(str(e))
            return validation_results


# Example usage and testing
async def demo_local_dashboard_service():
    """Demonstrate the Local Dashboard Service functionality."""
    print(" Local Dashboard Service Demo - Issue #49")
    print("=" * 50)

    try:
        # Initialize service
        config = LocalDashboardConfig.from_env()
        service = LocalDashboardService(config)

        print(" Local dashboard service initialized")

        # 1. Set up local dashboard resources
        print("\n Setting up local dashboard resources...")
        setup_result = await service.setup_dashboard_resources()
        print("Data source created: {0}".format(setup_result["data_source_created"]))
        print("Datasets created: {0}".format(len(setup_result["datasets_created"])))
        print("Analyses created: {0}".format(len(setup_result["analyses_created"])))
        print("Dashboards created: {0}".format(len(setup_result["dashboards_created"])))

        # 2. Create specific dashboard layouts
        print("\n Creating dashboard layouts...")
        for layout_type in DashboardType:
            if layout_type != DashboardType.COMPREHENSIVE:
                layout_result = await service.create_dashboard_layout(layout_type)
                print(
                    "{0}: {1}".format(
                        layout_type.value,
                        "ok" if layout_result["success"] else "failed",
                    )
                )

        # 3. Set up real-time updates
        print("\n Setting up refresh schedules...")
        updates_result = await service.setup_real_time_updates()
        print(
            "Refresh schedules: {0}".format(
                "ok" if updates_result["success"] else "failed"
            )
        )

        # 4. Validate setup
        print("\n Validating setup...")
        validation_result = await service.validate_setup()
        print(
            "Overall validation: {0}".format(
                "ok" if validation_result["overall_valid"] else "failed"
            )
        )

        print("\n Local Dashboard Service demo completed!")

    except Exception as e:
        print("Demo failed: {0}".format(e))


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_local_dashboard_service())
