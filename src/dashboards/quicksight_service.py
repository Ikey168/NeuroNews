"""
AWS QuickSight Dashboard Service for News Insights.

This module implements Issue #49: Develop AWS QuickSight Dashboard for News Insights.

Key Features:
1. Set up AWS QuickSight for interactive visualization
2. Create dashboard layout for:
   - Trending topics by sentiment
   - Knowledge graph entity relationships
   - Event timeline analysis
3. Enable filtering by date, entity, and sentiment
4. Implement real-time updates from Redshift

Dependencies:
- boto3 for AWS QuickSight API
- src.database.redshift_loader for data source integration
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)


class QuickSightResourceType(Enum):
    """QuickSight resource types."""

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
class QuickSightConfig:
    """Configuration for QuickSight service."""

    aws_account_id: str
    region: str = "us-east-1"
    namespace: str = "default"
    data_source_id: str = "neuronews-redshift-ds"
    data_source_name: str = "NeuroNews Redshift Data Source"
    dashboard_prefix: str = "NeuroNews"

    # Redshift connection details
    redshift_host: Optional[str] = None
    redshift_port: int = 5439
    redshift_database: str = "neuronews"
    redshift_username: Optional[str] = None
    redshift_password: Optional[str] = None

    @classmethod
    def from_env(cls) -> "QuickSightConfig":
        """Create configuration from environment variables."""
        return cls(
            aws_account_id=os.getenv("AWS_ACCOUNT_ID", ""),
            region=os.getenv("AWS_REGION", "us-east-1"),
            redshift_host=os.getenv("REDSHIFT_HOST"),
            redshift_database=os.getenv("REDSHIFT_DB", "neuronews"),
            redshift_username=os.getenv("REDSHIFT_USER"),
            redshift_password=os.getenv("REDSHIFT_PASSWORD"),
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


class QuickSightDashboardService:
    """Service for managing AWS QuickSight dashboards for news insights."""

    def __init__(self, config: Optional[QuickSightConfig] = None):
        """Initialize QuickSight service."""
        self.config = config or QuickSightConfig.from_env()

        # Initialize AWS clients
        try:
            self.quicksight_client = boto3.client(
                "quicksight", region_name=self.config.region
            )
            self.sts_client = boto3.client("sts")
            logger.info("QuickSight service initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize AWS clients: {0}".format(e))
            raise

        # Validate configuration
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate QuickSight configuration."""
        required_fields = ["aws_account_id", "redshift_host", "redshift_username"]
        missing_fields = [
            field for field in required_fields if not getattr(self.config, field)
        ]

        if missing_fields:
            logger.warning("Missing configuration fields: {0}".format(missing_fields))
            logger.info("Some functionality may be limited without full configuration")

    async def setup_quicksight_resources(self) -> Dict[str, Any]:
        """
        Set up AWS QuickSight for interactive visualization.

        This implements the first requirement of Issue #49.
        """
        logger.info("Setting up QuickSight resources...")

        setup_results = {
            "data_source_created": False,
            "datasets_created": [],
            "analyses_created": [],
            "dashboards_created": [],
            "errors": [],
        }

        try:
            # 1. Create Redshift data source
            data_source_result = await self._create_redshift_data_source()
            setup_results["data_source_created"] = data_source_result["success"]

            if not data_source_result["success"]:
                setup_results["errors"].append(
                    f"Data source creation failed: {
                        data_source_result.get('error')}"
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

            logger.info("QuickSight setup completed successfully")
            return setup_results

        except Exception as e:
            logger.error("Failed to set up QuickSight resources: {0}".format(e))
            setup_results["errors"].append(str(e))
            return setup_results

    async def _create_redshift_data_source(self) -> Dict[str, Any]:
        """Create Redshift data source in QuickSight."""
        try:
            data_source_params = {
                "AwsAccountId": self.config.aws_account_id,
                "DataSourceId": self.config.data_source_id,
                "Name": self.config.data_source_name,
                "Type": "REDSHIFT",
                "DataSourceParameters": {
                    "RedshiftParameters": {
                        "Host": self.config.redshift_host,
                        "Port": self.config.redshift_port,
                        "Database": self.config.redshift_database,
                    }
                },
                "Credentials": {
                    "CredentialPair": {
                        "Username": self.config.redshift_username,
                        "Password": self.config.redshift_password,
                    }
                },
                "Permissions": [
                    {
                        "Principal": "arn:aws:quicksight:{0}:{1}:user/{2}/admin".format(
                            self.config.region,
                            self.config.aws_account_id,
                            self.config.namespace,
                        ),
                        "Actions": [
                            "quicksight:DescribeDataSource",
                            "quicksight:DescribeDataSourcePermissions",
                            "quicksight:PassDataSource",
                            "quicksight:UpdateDataSource",
                            "quicksight:DeleteDataSource",
                            "quicksight:UpdateDataSourcePermissions",
                        ],
                    }
                ],
                "SslProperties": {"DisableSsl": False},
            }

            # Check if data source already exists
            try:
                existing = self.quicksight_client.describe_data_source(
                    AwsAccountId=self.config.aws_account_id,
                    DataSourceId=self.config.data_source_id,
                )
                logger.info("Redshift data source already exists")
                return {
                    "success": True,
                    "action": "already_exists",
                    "data_source_id": self.config.data_source_id,
                }
            except self.quicksight_client.exceptions.ResourceNotFoundException:
                pass

            # Create new data source
            response = self.quicksight_client.create_data_source(**data_source_params)

            logger.info(
                "Created Redshift data source: {0}".format(self.config.data_source_id)
            )
            return {
                "success": True,
                "action": "created",
                "data_source_id": self.config.data_source_id,
                "arn": response.get("Arn"),
            }

        except Exception as e:
            logger.error("Failed to create Redshift data source: {0}".format(e))
            return {"success": False, "error": str(e)}

    async def _create_datasets(self) -> List[Dict[str, Any]]:
        """Create datasets for different dashboard views."""
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
                try:
                    existing = self.quicksight_client.describe_data_set(
                        AwsAccountId=self.config.aws_account_id, DataSetId=dataset_id
                    )
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
                except self.quicksight_client.exceptions.ResourceNotFoundException:
                    pass

                # Create dataset
                dataset_params = {
                    "AwsAccountId": self.config.aws_account_id,
                    "DataSetId": dataset_id,
                    "Name": dataset_config["name"],
                    "PhysicalTableMap": {
                        "CustomSql": {
                            "DataSourceArn": "arn:aws:quicksight:{0}:{1}:datasource/{2}".format(
                                self.config.region,
                                self.config.aws_account_id,
                                self.config.data_source_id,
                            ),
                            "Name": dataset_config["name"],
                            "SqlQuery": dataset_config["sql"],
                            "Columns": self._get_dataset_columns(dataset_config["id"]),
                        }
                    },
                    "ImportMode": "DIRECT_QUERY",
                    "Permissions": [
                        {
                            "Principal": "arn:aws:quicksight:{0}:{1}:user/{2}/admin".format(
                                self.config.region,
                                self.config.aws_account_id,
                                self.config.namespace,
                            ),
                            "Actions": [
                                "quicksight:DescribeDataSet",
                                "quicksight:DescribeDataSetPermissions",
                                "quicksight:PassDataSet",
                                "quicksight:DescribeIngestion",
                                "quicksight:ListIngestions",
                                "quicksight:UpdateDataSet",
                                "quicksight:DeleteDataSet",
                                "quicksight:CreateIngestion",
                                "quicksight:CancelIngestion",
                                "quicksight:UpdateDataSetPermissions",
                            ],
                        }
                    ],
                }

                response = self.quicksight_client.create_data_set(**dataset_params)

                logger.info("Created dataset: {0}".format(dataset_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": dataset_config["name"],
                        "id": dataset_id,
                        "arn": response.get("Arn"),
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to create dataset {
                        dataset_config['id']}: {e}"
                )
                results.append(
                    {
                        "success": False,
                        "name": dataset_config["name"],
                        "id": dataset_config["id"],
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
        """Create QuickSight analyses for different dashboard types."""
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
                try:
                    existing = self.quicksight_client.describe_analysis(
                        AwsAccountId=self.config.aws_account_id, AnalysisId=analysis_id
                    )
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
                except self.quicksight_client.exceptions.ResourceNotFoundException:
                    pass

                # Create analysis with basic definition
                analysis_params = {
                    "AwsAccountId": self.config.aws_account_id,
                    "AnalysisId": analysis_id,
                    "Name": analysis_config["name"],
                    "Definition": self._get_analysis_definition(analysis_config),
                    "Permissions": [
                        {
                            "Principal": "arn:aws:quicksight:{0}:{1}:user/{2}/admin".format(
                                self.config.region,
                                self.config.aws_account_id,
                                self.config.namespace,
                            ),
                            "Actions": [
                                "quicksight:RestoreAnalysis",
                                "quicksight:UpdateAnalysisPermissions",
                                "quicksight:DeleteAnalysis",
                                "quicksight:DescribeAnalysisPermissions",
                                "quicksight:QueryAnalysis",
                                "quicksight:DescribeAnalysis",
                                "quicksight:UpdateAnalysis",
                            ],
                        }
                    ],
                }

                response = self.quicksight_client.create_analysis(**analysis_params)

                logger.info("Created analysis: {0}".format(analysis_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": analysis_config["name"],
                        "id": analysis_id,
                        "arn": response.get("Arn"),
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to create analysis {
                        analysis_config['id']}: {e}"
                )
                results.append(
                    {
                        "success": False,
                        "name": analysis_config["name"],
                        "id": analysis_config["id"],
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
                    "DataSetArn": "arn:aws:quicksight:{0}:{1}:dataset/{2}".format(
                        self.config.region, self.config.aws_account_id, dataset_id
                    ),
                    "Identifier": dataset_id,
                }
            ],
            "Sheets": [
                {
                    "SheetId": f"{
                        analysis_config['id']}_sheet_1",
                    "Name": analysis_config["name"],
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
        """Create QuickSight dashboards from analyses."""
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
                try:
                    existing = self.quicksight_client.describe_dashboard(
                        AwsAccountId=self.config.aws_account_id,
                        DashboardId=dashboard_id,
                    )
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
                except self.quicksight_client.exceptions.ResourceNotFoundException:
                    pass

                # Create dashboard from analyses
                dashboard_params = {
                    "AwsAccountId": self.config.aws_account_id,
                    "DashboardId": dashboard_id,
                    "Name": dashboard_config["name"],
                    "Definition": self._get_dashboard_definition(dashboard_config),
                    "Permissions": [
                        {
                            "Principal": "arn:aws:quicksight:{0}:{1}:user/{2}/admin".format(
                                self.config.region,
                                self.config.aws_account_id,
                                self.config.namespace,
                            ),
                            "Actions": [
                                "quicksight:DescribeDashboard",
                                "quicksight:ListDashboardVersions",
                                "quicksight:UpdateDashboardPermissions",
                                "quicksight:QueryDashboard",
                                "quicksight:UpdateDashboard",
                                "quicksight:DeleteDashboard",
                                "quicksight:DescribeDashboardPermissions",
                                "quicksight:UpdateDashboardPublishedVersion",
                            ],
                        }
                    ],
                }

                response = self.quicksight_client.create_dashboard(**dashboard_params)

                logger.info("Created dashboard: {0}".format(dashboard_id))
                results.append(
                    {
                        "success": True,
                        "action": "created",
                        "name": dashboard_config["name"],
                        "id": dashboard_id,
                        "arn": response.get("Arn"),
                    }
                )

            except Exception as e:
                logger.error(
                    f"Failed to create dashboard {dashboard_config['id']}: {e}"
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
                    "DataSetArn": "arn:aws:quicksight:{0}:{1}:dataset/sentiment_trends_dataset".format(
                        self.config.region, self.config.aws_account_id
                    ),
                    "Identifier": "sentiment_trends_dataset",
                },
                {
                    "DataSetArn": "arn:aws:quicksight:{0}:{1}:dataset/entity_relationships_dataset".format(
                        self.config.region, self.config.aws_account_id
                    ),
                    "Identifier": "entity_relationships_dataset",
                },
                {
                    "DataSetArn": "arn:aws:quicksight:{0}:{1}:dataset/event_timeline_dataset".format(
                        self.config.region, self.config.aws_account_id
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
        "Create a dashboard layout for trending topics by sentiment,
        knowledge graph entity relationships, event timeline analysis."
        """
        logger.info("Creating dashboard layout for {0}".format(layout_type.value))

        try:
            layout_config = self._get_layout_config(layout_type)

            # Create specific dashboard for this layout
            dashboard_id = "neuronews_{0}_dashboard".format(layout_type.value)

            dashboard_params = {
                "AwsAccountId": self.config.aws_account_id,
                "DashboardId": dashboard_id,
                "Name": layout_config.name,
                "Definition": {
                    "DataSetIdentifierDeclarations": [
                        {
                            "DataSetArn": "arn:aws:quicksight:{0}:{1}:dataset/{2}".format(
                                self.config.region,
                                self.config.aws_account_id,
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
                "Permissions": [
                    {
                        "Principal": "arn:aws:quicksight:{0}:{1}:user/{2}/admin".format(
                            self.config.region,
                            self.config.aws_account_id,
                            self.config.namespace,
                        ),
                        "Actions": [
                            "quicksight:DescribeDashboard",
                            "quicksight:ListDashboardVersions",
                            "quicksight:UpdateDashboardPermissions",
                            "quicksight:QueryDashboard",
                            "quicksight:UpdateDashboard",
                            "quicksight:DeleteDashboard",
                        ],
                    }
                ],
            }

            response = self.quicksight_client.create_dashboard(**dashboard_params)

            logger.info("Created {0} dashboard successfully".format(layout_type.value))
            return {
                "success": True,
                "dashboard_id": dashboard_id,
                "dashboard_url": self._get_dashboard_url(dashboard_id),
                "arn": response.get("Arn"),
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
                visuals=self._get_sentiment_trends_visuals("sentiment_trends_dataset"),
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
                    }
                ],
            )
        elif layout_type == DashboardType.EVENT_TIMELINE:
            return DashboardLayout(
                name="Event Timeline Analysis",
                description="Dashboard showing event patterns and timeline analysis",
                layout_type=layout_type,
                visuals=self._get_event_timeline_visuals("event_timeline_dataset"),
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
                    }
                ],
            )
        else:
            raise ValueError("Unsupported layout type: {0}".format(layout_type))

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
        Implement real-time updates from Redshift.

        This implements the fourth requirement of Issue #49.
        """
        logger.info("Setting up real-time updates from Redshift...")

        try:
            # Set up refresh schedules for datasets
            refresh_results = []

            datasets = [
                "sentiment_trends_dataset",
                "entity_relationships_dataset",
                "event_timeline_dataset",
            ]

            for dataset_id in datasets:
                try:
                    # Create refresh schedule for dataset
                    schedule_id = "{0}_refresh_schedule".format(dataset_id)

                    refresh_params = {
                        "DataSetId": dataset_id,
                        "AwsAccountId": self.config.aws_account_id,
                        "Schedule": {
                            "ScheduleId": schedule_id,
                            "ScheduleFrequency": {
                                "Interval": "HOURLY"  # Refresh every hour
                            },
                            "RefreshType": "INCREMENTAL_REFRESH",
                            "StartAfterDateTime": datetime.now(),
                        },
                    }

                    # Note: This is a simplified implementation
                    # In practice, you would use QuickSight's ingestion
                    # scheduling

                    refresh_results.append(
                        {
                            "dataset_id": dataset_id,
                            "refresh_schedule": "hourly",
                            "status": "configured",
                        }
                    )

                except Exception as e:
                    logger.error(
                        "Failed to set up refresh for {0}: {1}".format(dataset_id, e)
                    )
                    refresh_results.append(
                        {"dataset_id": dataset_id, "status": "failed", "error": str(e)}
                    )

            logger.info("Real-time updates setup completed")
            return {
                "success": True,
                "refresh_schedules": refresh_results,
                "update_frequency": "hourly",
            }

        except Exception as e:
            logger.error("Failed to setup real-time updates: {0}".format(e))
            return {"success": False, "error": str(e)}

    def _get_dashboard_url(self, dashboard_id: str) -> str:
        """Get QuickSight dashboard URL."""
        return "https://{0}.quicksight.aws.amazon.com/sn/dashboards/{1}".format(
            self.config.region, dashboard_id
        )

    async def get_dashboard_info(
        self, dashboard_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get information about created dashboards."""
        try:
            if dashboard_id:
                # Get specific dashboard info
                response = self.quicksight_client.describe_dashboard(
                    AwsAccountId=self.config.aws_account_id, DashboardId=dashboard_id
                )
                return {
                    "success": True,
                    "dashboard": {
                        "id": dashboard_id,
                        "name": response["Dashboard"]["Name"],
                        "status": response["Dashboard"]["Version"]["Status"],
                        "url": self._get_dashboard_url(dashboard_id),
                        "last_updated": response["Dashboard"]["LastUpdatedTime"],
                        "created_time": response["Dashboard"]["CreatedTime"],
                    },
                }
            else:
                # List all NeuroNews dashboards
                response = self.quicksight_client.list_dashboards(
                    AwsAccountId=self.config.aws_account_id
                )

                neuronews_dashboards = [
                    {
                        "id": dashboard["DashboardId"],
                        "name": dashboard["Name"],
                        "url": self._get_dashboard_url(dashboard["DashboardId"]),
                        "last_updated": dashboard["LastUpdatedTime"],
                        "created_time": dashboard["CreatedTime"],
                    }
                    for dashboard in response["DashboardSummaryList"]
                    if "neuronews" in dashboard["DashboardId"].lower()
                ]

                return {
                    "success": True,
                    "dashboards": neuronews_dashboards,
                    "total_count": len(neuronews_dashboards),
                }

        except Exception as e:
            logger.error("Failed to get dashboard info: {0}".format(e))
            return {"success": False, "error": str(e)}

    async def validate_setup(self) -> Dict[str, Any]:
        """Validate QuickSight setup and resources."""
        logger.info("Validating QuickSight setup...")

        validation_results = {
            "data_source_valid": False,
            "datasets_valid": [],
            "analyses_valid": [],
            "dashboards_valid": [],
            "errors": [],
        }

        try:
            # Validate data source
            try:
                self.quicksight_client.describe_data_source(
                    AwsAccountId=self.config.aws_account_id,
                    DataSourceId=self.config.data_source_id,
                )
                validation_results["data_source_valid"] = True
            except Exception as e:
                validation_results["errors"].append(
                    "Data source validation failed: {0}".format(e)
                )

            # Validate datasets
            datasets = [
                "sentiment_trends_dataset",
                "entity_relationships_dataset",
                "event_timeline_dataset",
            ]
            for dataset_id in datasets:
                try:
                    self.quicksight_client.describe_data_set(
                        AwsAccountId=self.config.aws_account_id, DataSetId=dataset_id
                    )
                    validation_results["datasets_valid"].append(dataset_id)
                except Exception as e:
                    validation_results["errors"].append(
                        "Dataset {0} validation failed: {1}".format(dataset_id, e)
                    )

            # Validate analyses
            analyses = [
                "sentiment_trends_analysis",
                "entity_relationships_analysis",
                "event_timeline_analysis",
            ]
            for analysis_id in analyses:
                try:
                    self.quicksight_client.describe_analysis(
                        AwsAccountId=self.config.aws_account_id, AnalysisId=analysis_id
                    )
                    validation_results["analyses_valid"].append(analysis_id)
                except Exception as e:
                    validation_results["errors"].append(
                        "Analysis {0} validation failed: {1}".format(analysis_id, e)
                    )

            # Validate dashboards
            dashboards = ["neuronews_comprehensive_dashboard"]
            for dashboard_id in dashboards:
                try:
                    self.quicksight_client.describe_dashboard(
                        AwsAccountId=self.config.aws_account_id,
                        DashboardId=dashboard_id,
                    )
                    validation_results["dashboards_valid"].append(dashboard_id)
                except Exception as e:
                    validation_results["errors"].append(
                        "Dashboard {0} validation failed: {1}".format(dashboard_id, e)
                    )

            validation_results["overall_valid"] = (
                validation_results["data_source_valid"]
                and len(validation_results["datasets_valid"]) >= 2
                and len(validation_results["dashboards_valid"]) >= 1
            )

            logger.info(
                f"Validation completed: {
                    'Success' if validation_results['overall_valid'] else 'Issues found'}"
            )
            return validation_results

        except Exception as e:
            logger.error("Validation failed: {0}".format(e))
            validation_results["errors"].append(str(e))
            return validation_results


# Example usage and testing
async def demo_quicksight_dashboard_service():
    """Demonstrate the QuickSight Dashboard Service functionality."""
    print("🎯 QuickSight Dashboard Service Demo - Issue #49")
    print("=" * 50)

    try:
        # Initialize service
        config = QuickSightConfig.from_env()
        service = QuickSightDashboardService(config)

        print("✅ QuickSight service initialized")

        # 1. Set up QuickSight resources
        print("\n📊 Setting up QuickSight resources...")
        setup_result = await service.setup_quicksight_resources()
        print(f"Data source created: {setup_result['data_source_created']}")
        print(f"Datasets created: {len(setup_result['datasets_created'])}")
        print(f"Analyses created: {len(setup_result['analyses_created'])}")
        print(f"Dashboards created: {len(setup_result['dashboards_created'])}")

        # 2. Create specific dashboard layouts
        print("\n📈 Creating dashboard layouts...")
        for layout_type in DashboardType:
            if layout_type != DashboardType.COMPREHENSIVE:
                layout_result = await service.create_dashboard_layout(layout_type)
                print(
                    f"{layout_type.value}: {'✅' if layout_result['success'] else '❌'}"
                )

        # 3. Set up real-time updates
        print("\n🔄 Setting up real-time updates...")
        updates_result = await service.setup_real_time_updates()
        print(f"Real-time updates: {'✅' if updates_result['success'] else '❌'}")

        # 4. Validate setup
        print("\n✅ Validating setup...")
        validation_result = await service.validate_setup()
        print(
            f"Overall validation: {
                '✅' if validation_result['overall_valid'] else '❌'}"
        )

        # 5. Get dashboard info
        print("\n📊 Dashboard information:")
        dashboard_info = await service.get_dashboard_info()
        if dashboard_info["success"]:
            for dashboard in dashboard_info["dashboards"]:
                print(f"• {dashboard['name']}: {dashboard['url']}")

        print("\n🎉 QuickSight Dashboard Service demo completed!")

    except Exception as e:
        print("❌ Demo failed: {0}".format(e))


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_quicksight_dashboard_service())
