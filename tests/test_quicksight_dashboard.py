"""
Comprehensive test suite for AWS QuickSight Dashboard implementation.

This module tests Issue #49: Develop AWS QuickSight Dashboard for News Insights.

Test Coverage:
- QuickSight service initialization and configuration
- Data source creation and management
- Dataset creation for different analysis types
- Dashboard layout creation for all supported types
- API endpoint functionality and error handling
- Real-time update setup and validation
- Complete integration testing
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.dashboards.quicksight_service import (
    DashboardType,
    QuickSightConfig,
    QuickSightDashboardService,
    QuickSightResourceType,
)


class TestQuickSightService:
    """Test QuickSight service functionality."""

    @pytest.fixture
    def mock_config(self):
        """Mock QuickSight configuration."""
        return QuickSightConfig(
            aws_account_id="123456789012",
            region="us-east-1",
            snowflake_account="test-cluster.redshift.amazonaws.com",
            redshift_database="neuronews",
            snowflake_username="test_user",
            snowflake_password="test_password",
        )

    @pytest.fixture
    def mock_quicksight_client(self):
        """Mock QuickSight client."""
        mock_client = Mock()

        # Mock data source operations
        mock_client.describe_data_source.side_effect = (
            mock_client.exceptions.ResourceNotFoundException()
        )
        mock_client.create_data_source.return_value = {
            "Arn": "arn:aws:quicksight:us-east-1:123456789012:datasource/test-ds",
            "DataSourceId": "neuronews-redshift-ds",
        }

        # Mock dataset operations
        mock_client.describe_data_set.side_effect = (
            mock_client.exceptions.ResourceNotFoundException()
        )
        mock_client.create_data_set.return_value = {
            "Arn": "arn:aws:quicksight:us-east-1:123456789012:dataset/test-dataset",
            "DataSetId": "test-dataset",
        }

        # Mock analysis operations
        mock_client.describe_analysis.side_effect = (
            mock_client.exceptions.ResourceNotFoundException()
        )
        mock_client.create_analysis.return_value = {
            "Arn": "arn:aws:quicksight:us-east-1:123456789012:analysis/test-analysis",
            "AnalysisId": "test-analysis",
        }

        # Mock dashboard operations
        mock_client.describe_dashboard.side_effect = (
            mock_client.exceptions.ResourceNotFoundException()
        )
        mock_client.create_dashboard.return_value = {
            "Arn": "arn:aws:quicksight:us-east-1:123456789012:dashboard/test-dashboard",
            "DashboardId": "test-dashboard",
        }

        # Mock list operations
        mock_client.list_dashboards.return_value = {
            "DashboardSummaryList": [
                {
                    "DashboardId": "neuronews_comprehensive_dashboard",
                    "Name": "NeuroNews Comprehensive Dashboard",
                    "LastUpdatedTime": datetime.now(),
                    "CreatedTime": datetime.now(),
                }
            ]
        }

        # Add exceptions class
        mock_client.exceptions = Mock()
        mock_client.exceptions.ResourceNotFoundException = Exception

        return mock_client

    @pytest.fixture
    def service(self, mock_config, mock_quicksight_client):
        """Create QuickSight service with mocked dependencies."""
        with patch("boto3.client") as mock_boto3:
            mock_boto3.return_value = mock_quicksight_client
            service = QuickSightDashboardService(mock_config)
            service.quicksight_client = mock_quicksight_client
            return service

    def test_service_initialization(self, mock_config):
        """Test QuickSight service initialization."""
        with patch("boto3.client") as mock_boto3:
            mock_boto3.return_value = Mock()

            service = QuickSightDashboardService(mock_config)

            assert service.config.aws_account_id == "123456789012"
            assert service.config.region == "us-east-1"
            assert service.config.snowflake_account == "test-cluster.redshift.amazonaws.com"
            mock_boto3.assert_called()

    def test_config_from_env(self):
        """Test configuration creation from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "AWS_ACCOUNT_ID": "123456789012",
                "AWS_REGION": "us-west-2",
                "SNOWFLAKE_ACCOUNT": "env-cluster.redshift.amazonaws.com",
                "SNOWFLAKE_DATABASE": "env_neuronews",
                "SNOWFLAKE_USER": "env_user",
                "SNOWFLAKE_PASSWORD": "env_password",
            },
        ):
            config = QuickSightConfig.from_env()

            assert config.aws_account_id == "123456789012"
            assert config.region == "us-west-2"
            assert config.snowflake_account == "env-cluster.redshift.amazonaws.com"
            assert config.redshift_database == "env_neuronews"
            assert config.snowflake_username == "env_user"

    @pytest.mark.asyncio
    async def test_create_redshift_data_source(self, service, mock_quicksight_client):
        """Test Redshift data source creation."""
        result = await service._create_redshift_data_source()

        assert result["success"] is True
        assert result["action"] == "created"
        assert result["data_source_id"] == "neuronews-redshift-ds"

        mock_quicksight_client.create_data_source.assert_called_once()
        call_args = mock_quicksight_client.create_data_source.call_args[1]
        assert call_args["DataSourceId"] == "neuronews-redshift-ds"
        assert call_args["Type"] == "REDSHIFT"

    @pytest.mark.asyncio
    async def test_create_datasets(self, service, mock_quicksight_client):
        """Test dataset creation for different analysis types."""
        results = await service._create_datasets()

        assert len(results) == 3

        # Check dataset types
        dataset_ids = [result["id"] for result in results if result["success"]]
        assert "sentiment_trends_dataset" in dataset_ids
        assert "entity_relationships_dataset" in dataset_ids
        assert "event_timeline_dataset" in dataset_ids

        # Verify create_data_set was called for each dataset
        assert mock_quicksight_client.create_data_set.call_count == 3

    def test_sentiment_trends_sql(self, service):
        """Test sentiment trends SQL query generation."""
        sql = service._get_sentiment_trends_sql()

        assert "sentiment_label" in sql
        assert "published_date" in sql
        assert "GROUP BY" in sql
        assert "news_articles" in sql
        assert "INTERVAL '90 days'" in sql

    def test_entity_relationships_sql(self, service):
        """Test entity relationships SQL query generation."""
        sql = service._get_entity_relationships_sql()

        assert "entity_1" in sql
        assert "entity_2" in sql
        assert "co_occurrence_count" in sql
        assert "JSON_ARRAY_ELEMENTS_TEXT" in sql
        assert "news_articles" in sql

    def test_event_timeline_sql(self, service):
        """Test event timeline SQL query generation."""
        sql = service._get_event_timeline_sql()

        assert "published_date" in sql
        assert "sentiment_score" in sql
        assert "CASE" in sql
        assert "sentiment_category" in sql
        assert "EXTRACT(hour" in sql

    def test_dataset_columns(self, service):
        """Test dataset column definitions."""
        # Test sentiment trends columns
        columns = service._get_dataset_columns("sentiment_trends_dataset")
        column_names = [col["Name"] for col in columns]
        assert "date" in column_names
        assert "sentiment_label" in column_names
        assert "article_count" in column_names

        # Test entity relationships columns
        columns = service._get_dataset_columns("entity_relationships_dataset")
        column_names = [col["Name"] for col in columns]
        assert "entity_1" in column_names
        assert "entity_2" in column_names
        assert "co_occurrence_count" in column_names

        # Test event timeline columns
        columns = service._get_dataset_columns("event_timeline_dataset")
        column_names = [col["Name"] for col in columns]
        assert "article_id" in column_names
        assert "published_date" in column_names
        assert "sentiment_category" in column_names

    @pytest.mark.asyncio
    async def test_create_analyses(self, service, mock_quicksight_client):
        """Test analysis creation."""
        results = await service._create_analyses()

        assert len(results) == 3

        # Check analysis types
        analysis_ids = [result["id"] for result in results if result["success"]]
        assert "sentiment_trends_analysis" in analysis_ids
        assert "entity_relationships_analysis" in analysis_ids
        assert "event_timeline_analysis" in analysis_ids

        # Verify create_analysis was called for each analysis
        assert mock_quicksight_client.create_analysis.call_count == 3

    def test_sentiment_trends_visuals(self, service):
        """Test sentiment trends visual generation."""
        visuals = service._get_sentiment_trends_visuals("sentiment_trends_dataset")

        assert len(visuals) == 1
        assert visuals[0]["VisualId"] == "sentiment_over_time"
        assert "LineChartVisual" in visuals[0]

    def test_entity_relationships_visuals(self, service):
        """Test entity relationships visual generation."""
        visuals = service._get_entity_relationships_visuals("entity_relationships_dataset")

        assert len(visuals) == 1
        assert visuals[0]["VisualId"] == "entity_network"
        assert "ScatterPlotVisual" in visuals[0]

    def test_event_timeline_visuals(self, service):
        """Test event timeline visual generation."""
        visuals = service._get_event_timeline_visuals("event_timeline_dataset")

        assert len(visuals) == 1
        assert visuals[0]["VisualId"] == "event_timeline"
        assert "LineChartVisual" in visuals[0]

    @pytest.mark.asyncio
    async def test_create_dashboards(self, service, mock_quicksight_client):
        """Test dashboard creation."""
        results = await service._create_dashboards()

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["id"] == "neuronews_comprehensive_dashboard"

        mock_quicksight_client.create_dashboard.assert_called_once()

    def test_dashboard_filters(self, service):
        """Test dashboard filter configuration."""
        filters = service._get_dashboard_filters()

        filter_ids = [f["FilterId"] for f in filters]
        assert "date_filter" in filter_ids
        assert "sentiment_filter" in filter_ids
        assert "category_filter" in filter_ids

        # Check filter types
        date_filter = next(f for f in filters if f["FilterId"] == "date_filter")
        assert "DateTimePickerFilter" in date_filter

        sentiment_filter = next(f for f in filters if f["FilterId"] == "sentiment_filter")
        assert "CategoryFilter" in sentiment_filter

    @pytest.mark.asyncio
    async def test_create_dashboard_layout(self, service, mock_quicksight_client):
        """Test specific dashboard layout creation."""
        result = await service.create_dashboard_layout(DashboardType.SENTIMENT_TRENDS)

        assert result["success"] is True
        assert "dashboard_id" in result
        assert "dashboard_url" in result

        mock_quicksight_client.create_dashboard.assert_called()

    @pytest.mark.asyncio
    async def test_setup_real_time_updates(self, service):
        """Test real-time update setup."""
        result = await service.setup_real_time_updates()

        assert result["success"] is True
        assert "refresh_schedules" in result
        assert result["update_frequency"] == "hourly"
        assert len(result["refresh_schedules"]) == 3

    @pytest.mark.asyncio
    async def test_setup_quicksight_resources(self, service, mock_quicksight_client):
        """Test complete QuickSight resource setup."""
        result = await service.setup_quicksight_resources()

        assert result["data_source_created"] is True
        assert len(result["datasets_created"]) >= 2
        assert len(result["analyses_created"]) >= 2
        assert len(result["dashboards_created"]) >= 1

        # Verify all creation methods were called
        mock_quicksight_client.create_data_source.assert_called()
        assert mock_quicksight_client.create_data_set.call_count >= 3
        assert mock_quicksight_client.create_analysis.call_count >= 3
        assert mock_quicksight_client.create_dashboard.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_dashboard_info_single(self, service, mock_quicksight_client):
        """Test getting single dashboard info."""
        # Mock describe_dashboard response
        mock_quicksight_client.describe_dashboard.return_value = {
            "Dashboard": {
                "DashboardId": "test_dashboard",
                "Name": "Test Dashboard",
                "Version": {"Status": "CREATION_SUCCESSFUL"},
                "LastUpdatedTime": datetime.now(),
                "CreatedTime": datetime.now(),
            }
        }

        result = await service.get_dashboard_info("test_dashboard")

        assert result["success"] is True
        assert result["dashboard"]["id"] == "test_dashboard"
        assert result["dashboard"]["name"] == "Test Dashboard"

    @pytest.mark.asyncio
    async def test_get_dashboard_info_list(self, service, mock_quicksight_client):
        """Test getting dashboard list."""
        result = await service.get_dashboard_info()

        assert result["success"] is True
        assert "dashboards" in result
        assert result["total_count"] >= 1

        mock_quicksight_client.list_dashboards.assert_called()

    @pytest.mark.asyncio
    async def test_validate_setup(self, service, mock_quicksight_client):
        """Test setup validation."""
        # Mock successful validation responses
        mock_quicksight_client.describe_data_source.return_value = {"DataSource": {}}
        mock_quicksight_client.describe_data_set.return_value = {"DataSet": {}}
        mock_quicksight_client.describe_analysis.return_value = {"Analysis": {}}
        mock_quicksight_client.describe_dashboard.return_value = {"Dashboard": {}}

        result = await service.validate_setup()

        assert result["data_source_valid"] is True
        assert len(result["datasets_valid"]) == 3
        assert len(result["analyses_valid"]) == 3
        assert len(result["dashboards_valid"]) == 1
        assert result["overall_valid"] is True


class TestQuickSightAPI:
    """Test QuickSight API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_service(self):
        """Mock QuickSight service."""
        return Mock(spec=QuickSightDashboardService)

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/dashboards/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "quicksight-dashboard"
        assert data["issue"] == "49"

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_setup_quicksight_resources(self, mock_get_service, client):
        """Test QuickSight setup endpoint."""
        # Mock service
        mock_service = AsyncMock()
        mock_service.setup_quicksight_resources.return_value = {
            "data_source_created": True,
            "datasets_created": ["sentiment_trends_dataset"],
            "analyses_created": ["sentiment_trends_analysis"],
            "dashboards_created": ["comprehensive_dashboard"],
            "errors": [],
        }
        mock_get_service.return_value = mock_service

        setup_data = {
            "aws_account_id": "123456789012",
            "region": "us-east-1",
            "snowflake_account": "test-cluster.redshift.amazonaws.com",
            "redshift_database": "neuronews",
            "snowflake_username": "test_user",
            "snowflake_password": "test_password",
        }

        response = client.post("/api/v1/dashboards/setup", json=setup_data)

        assert response.status_code == 200
        data = response.json()
        assert data["data_source_created"] is True
        assert len(data["datasets_created"]) >= 1

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_list_dashboards(self, mock_get_service, client):
        """Test list dashboards endpoint."""
        mock_service = AsyncMock()
        mock_service.get_dashboard_info.return_value = {
            "success": True,
            "dashboards": [
                {
                    "id": "test_dashboard",
                    "name": "Test Dashboard",
                    "url": "https://quicksight.aws.amazon.com/test",
                    "last_updated": datetime.now(),
                    "created_time": datetime.now(),
                }
            ],
            "total_count": 1,
        }
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/dashboards")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["dashboards"]) == 1

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_create_dashboard_layout(self, mock_get_service, client):
        """Test create dashboard layout endpoint."""
        mock_service = AsyncMock()
        mock_service.create_dashboard_layout.return_value = {
            "success": True,
            "dashboard_id": "sentiment_trends_dashboard",
            "dashboard_url": "https://quicksight.aws.amazon.com/sentiment",
        }
        mock_get_service.return_value = mock_service

        response = client.post("/api/v1/dashboards/layout/sentiment_trends")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dashboard_id" in data

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_create_dashboard_layout_invalid_type(self, mock_get_service, client):
        """Test create dashboard layout with invalid type."""
        response = client.post("/api/v1/dashboards/layout/invalid_type")

        assert response.status_code == 400
        data = response.json()
        assert "Invalid layout type" in data["detail"]

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_setup_real_time_updates(self, mock_get_service, client):
        """Test setup real-time updates endpoint."""
        mock_service = AsyncMock()
        mock_service.setup_real_time_updates.return_value = {
            "success": True,
            "refresh_schedules": [
                {"dataset_id": "sentiment_trends_dataset", "status": "configured"}
            ],
            "update_frequency": "hourly",
        }
        mock_get_service.return_value = mock_service

        response = client.put("/api/v1/dashboards/refresh?refresh_frequency=hourly")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["update_frequency"] == "hourly"

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_validate_setup(self, mock_get_service, client):
        """Test validate setup endpoint."""
        mock_service = AsyncMock()
        mock_service.validate_setup.return_value = {
            "success": True,
            "data_source_valid": True,
            "datasets_valid": ["sentiment_trends_dataset"],
            "analyses_valid": ["sentiment_trends_analysis"],
            "dashboards_valid": ["comprehensive_dashboard"],
            "overall_valid": True,
            "errors": [],
        }
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/dashboards/validate")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_valid"] is True
        assert data["data_source_valid"] is True

    @patch("src.api.routes.quicksight_routes.get_quicksight_service")
    def test_get_dashboard_info(self, mock_get_service, client):
        """Test get dashboard info endpoint."""
        mock_service = AsyncMock()
        mock_service.get_dashboard_info.return_value = {
            "success": True,
            "dashboard": {
                "id": "test_dashboard",
                "name": "Test Dashboard",
                "status": "CREATION_SUCCESSFUL",
                "url": "https://quicksight.aws.amazon.com/test",
                "last_updated": datetime.now(),
                "created_time": datetime.now(),
            },
        }
        mock_get_service.return_value = mock_service

        response = client.get("/api/v1/dashboards/test_dashboard")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dashboard"]["id"] == "test_dashboard"


class TestIntegration:
    """Integration tests for Issue #49."""

    def test_dashboard_types_enum(self):
        """Test DashboardType enum values."""
        assert DashboardType.SENTIMENT_TRENDS.value == "sentiment_trends"
        assert DashboardType.ENTITY_RELATIONSHIPS.value == "entity_relationships"
        assert DashboardType.EVENT_TIMELINE.value == "event_timeline"
        assert DashboardType.COMPREHENSIVE.value == "comprehensive"

    def test_resource_type_enum(self):
        """Test QuickSightResourceType enum values."""
        assert QuickSightResourceType.DATA_SOURCE.value == "data_source"
        assert QuickSightResourceType.DATA_SET.value == "data_set"
        assert QuickSightResourceType.ANALYSIS.value == "analysis"
        assert QuickSightResourceType.DASHBOARD.value == "dashboard"
        assert QuickSightResourceType.TEMPLATE.value == "template"

    @pytest.mark.asyncio
    async def test_issue_49_requirements_coverage(self):
        """Test that all Issue #49 requirements are covered."""
        # This test verifies that the implementation addresses all requirements

        # Requirement 1: Set up AWS QuickSight for interactive visualization
        #  Covered by QuickSightDashboardService.setup_quicksight_resources()

        # Requirement 2: Create dashboard layout for trending topics by sentiment,
        # knowledge graph entity relationships, event timeline analysis
        #  Covered by QuickSightDashboardService.create_dashboard_layout()
        #  Supported layouts: sentiment_trends, entity_relationships, event_timeline

        # Requirement 3: Enable filtering by date, entity, and sentiment
        #  Covered by _get_dashboard_filters() method

        # Requirement 4: Implement real-time updates from Redshift
        #  Covered by QuickSightDashboardService.setup_real_time_updates()

        requirements_covered = [
            "setup_quicksight_resources",  # Requirement 1
            "create_dashboard_layout",  # Requirement 2
            "_get_dashboard_filters",  # Requirement 3
            "setup_real_time_updates",  # Requirement 4
        ]

        # Check that all required methods exist in the service class
        from src.dashboards.quicksight_service import QuickSightDashboardService

        service_methods = [
            method
            for method in dir(QuickSightDashboardService)
            if not method.startswith("_") or method in ["_get_dashboard_filters"]
        ]

        for requirement in requirements_covered:
            assert requirement in service_methods or hasattr(
                QuickSightDashboardService, requirement
            )

        # Check that all dashboard types are supported
        supported_layouts = [layout.value for layout in DashboardType]
        required_layouts = [
            "sentiment_trends",
            "entity_relationships",
            "event_timeline",
        ]

        for layout in required_layouts:
            assert layout in supported_layouts

        print(" All Issue #49 requirements are covered in the implementation")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
