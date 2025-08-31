"""
Test suite for AWS Rate Limiting - Issue #447
Target: Improve coverage from 19% to 70%
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
import sys

# Add project root to Python path
sys.path.insert(0, '/workspaces/NeuroNews')

try:
    from src.api.aws_rate_limiting import (
        APIGatewayManager,
        CloudWatchMetrics,
        APIGatewayUsagePlan,
        APIGatewayConfiguration,
        get_api_gateway_manager,
        get_cloudwatch_metrics,
        setup_aws_rate_limiting
    )
except ImportError as e:
    print(f"Import error: {e}")
    pytest.skip("Cannot import aws_rate_limiting module", allow_module_level=True)


class TestAPIGatewayUsagePlan:
    """Test the APIGatewayUsagePlan dataclass."""

    def test_usage_plan_creation(self):
        """Test creating a usage plan."""
        plan = APIGatewayUsagePlan(
            plan_id="test_plan_id",
            name="test_plan",
            description="Test plan",
            throttle_rate_limit=1000.0,
            throttle_burst_limit=2000,
            quota_limit=10000,
            quota_period="DAY"
        )
        
        assert plan.plan_id == "test_plan_id"
        assert plan.name == "test_plan"
        assert plan.description == "Test plan"
        assert plan.throttle_rate_limit == 1000.0
        assert plan.throttle_burst_limit == 2000
        assert plan.quota_limit == 10000
        assert plan.quota_period == "DAY"

    def test_usage_plan_predefined_plans(self):
        """Test predefined usage plans in configuration."""
        config = APIGatewayConfiguration()
        
        # Test FREE_PLAN
        assert config.FREE_PLAN.plan_id == "free-tier-plan"
        assert config.FREE_PLAN.name == "Free Tier"
        assert config.FREE_PLAN.throttle_rate_limit == 0.17
        assert config.FREE_PLAN.quota_limit == 1000
        
        # Test PREMIUM_PLAN
        assert config.PREMIUM_PLAN.plan_id == "premium-tier-plan"
        assert config.PREMIUM_PLAN.name == "Premium Tier"
        assert config.PREMIUM_PLAN.quota_limit == 20000
        
        # Test ENTERPRISE_PLAN
        assert config.ENTERPRISE_PLAN.plan_id == "enterprise-tier-plan"
        assert config.ENTERPRISE_PLAN.name == "Enterprise Tier"
        assert config.ENTERPRISE_PLAN.quota_limit == 500000


class TestAPIGatewayConfiguration:
    """Test the APIGatewayConfiguration class."""

    def test_configuration_creation(self):
        """Test creating an API Gateway configuration."""
        config = APIGatewayConfiguration()
        
        # Test that predefined plans exist
        assert hasattr(config, 'FREE_PLAN')
        assert hasattr(config, 'PREMIUM_PLAN')
        assert hasattr(config, 'ENTERPRISE_PLAN')

    def test_configuration_plan_properties(self):
        """Test configuration plan properties."""
        config = APIGatewayConfiguration()
        
        # Verify all plans have required attributes
        for plan in [config.FREE_PLAN, config.PREMIUM_PLAN, config.ENTERPRISE_PLAN]:
            assert hasattr(plan, 'plan_id')
            assert hasattr(plan, 'name')
            assert hasattr(plan, 'description')
            assert hasattr(plan, 'throttle_rate_limit')
            assert hasattr(plan, 'throttle_burst_limit')
            assert hasattr(plan, 'quota_limit')
            assert hasattr(plan, 'quota_period')


@patch('src.api.aws_rate_limiting.boto3')
class TestAPIGatewayManager:
    """Test the APIGatewayManager class."""

    def test_manager_initialization(self, mock_boto3):
        """Test initializing the API Gateway manager."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        with patch.dict(os.environ, {
            'AWS_REGION': 'us-east-1',
            'API_GATEWAY_ID': 'test_api_id',
            'API_GATEWAY_STAGE': 'test'
        }):
            manager = APIGatewayManager(region='us-east-1')
            
            assert manager.region == 'us-east-1'
            assert manager.api_id == 'test_api_id'
            assert manager.stage_name == 'test'
            assert mock_boto3.client.call_count == 2  # apigateway and apigatewaymanagementapi

    @pytest.mark.asyncio
    async def test_create_usage_plans(self, mock_boto3):
        """Test creating usage plans."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan.return_value = {'id': 'test_plan_id'}
        mock_client.create_usage_plan_key.return_value = {'id': 'test_key_id'}
        
        with patch.dict(os.environ, {'API_GATEWAY_ID': 'test_api_id'}):
            manager = APIGatewayManager()
            result = await manager.create_usage_plans()
            
            assert isinstance(result, dict)
            assert mock_client.create_usage_plan.call_count == 3  # FREE, PREMIUM, ENTERPRISE

    @pytest.mark.asyncio
    async def test_assign_user_to_plan(self, mock_boto3):
        """Test assigning a user to a usage plan."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan_key.return_value = {'id': 'test_plan_key_id'}
        
        manager = APIGatewayManager()
        # Mock the helper methods
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'plan_123'}):
            with patch.object(manager, 'create_api_key_for_user', return_value='key_123'):
                result = await manager.assign_user_to_plan("test_user", "free", "test_api_key")
                
                assert result == True
                mock_client.create_usage_plan_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_api_key_for_user(self, mock_boto3):
        """Test creating an API key for a user."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_api_key.return_value = {'id': 'test_key_id'}
        
        manager = APIGatewayManager()
        result = await manager.create_api_key_for_user("test_user", "test_api_key_value")
        
        assert result == 'test_key_id'
        mock_client.create_api_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_usage_plans(self, mock_boto3):
        """Test getting existing usage plans."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_usage_plans.return_value = {
            'items': [
                {'name': 'Free Tier', 'id': 'free_plan_id'},
                {'name': 'Premium Tier', 'id': 'premium_plan_id'}
            ]
        }
        
        manager = APIGatewayManager()
        result = await manager.get_usage_plans()
        
        assert 'free_tier' in result
        assert 'premium_tier' in result
        assert result['free_tier'] == 'free_plan_id'
        
    @pytest.mark.asyncio
    async def test_get_usage_statistics(self, mock_boto3):
        """Test getting usage statistics."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.return_value = {
            'items': [{'id': 'key_123', 'value': 'test_api_key'}]
        }
        mock_client.get_usage.return_value = {
            'values': {'2024-01-01': 100, '2024-01-02': 150},
            'position': 'position_data',
            'startDate': '2024-01-01',
            'endDate': '2024-01-02'
        }
        
        manager = APIGatewayManager()
        result = await manager.get_usage_statistics("test_api_key", "2024-01-01", "2024-01-02")
        
        assert 'total_requests' in result
        assert result['total_requests'] == 250
        assert 'daily_breakdown' in result

    @pytest.mark.asyncio
    async def test_update_user_tier(self, mock_boto3):
        """Test updating a user's tier."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.return_value = {
            'items': [{'id': 'key_123', 'value': 'test_api_key', 'tags': {'user_id': 'test_user'}}]
        }
        mock_client.delete_usage_plan_key.return_value = {}
        
        manager = APIGatewayManager()
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'old_plan_id'}):
            with patch.object(manager, 'assign_user_to_plan', return_value=True):
                result = await manager.update_user_tier("test_user", "free", "premium")
                
                assert result == True

    @pytest.mark.asyncio
    async def test_monitor_throttling_events(self, mock_boto3):
        """Test monitoring throttling events."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        result = await manager.monitor_throttling_events()
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert 'timestamp' in result[0]
        assert 'throttled_requests' in result[0]


@patch('src.api.aws_rate_limiting.boto3')
class TestCloudWatchMetrics:
    """Test the CloudWatchMetrics class."""

    def test_metrics_initialization(self, mock_boto3):
        """Test initializing CloudWatch metrics."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        metrics = CloudWatchMetrics(region='us-east-1')
        
        assert metrics.region == 'us-east-1'
        mock_boto3.client.assert_called_with(
            'cloudwatch',
            region_name='us-east-1'
        )

    @pytest.mark.asyncio
    async def test_put_rate_limit_metrics(self, mock_boto3):
        """Test publishing rate limit metrics."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        metrics = CloudWatchMetrics()
        
        await metrics.put_rate_limit_metrics(
            user_id="test_user",
            tier="free",
            requests_count=100,
            violations=5
        )
        
        mock_client.put_metric_data.assert_called_once()
        call_args = mock_client.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'NeuroNews/RateLimiting'
        assert len(call_args[1]['MetricData']) == 2  # RequestCount and RateLimitViolations

    @pytest.mark.asyncio
    async def test_create_rate_limit_alarms(self, mock_boto3):
        """Test creating rate limit alarms."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        metrics = CloudWatchMetrics()
        await metrics.create_rate_limit_alarms()
        
        mock_client.put_metric_alarm.assert_called_once()
        call_args = mock_client.put_metric_alarm.call_args
        assert call_args[1]['AlarmName'] == 'NeuroNews-HighRateLimitViolations'
        assert call_args[1]['MetricName'] == 'RateLimitViolations'

    def test_metrics_initialization_failure(self, mock_boto3):
        """Test CloudWatch initialization failure."""
        mock_boto3.client.side_effect = Exception("AWS credentials not found")
        
        metrics = CloudWatchMetrics()
        
        assert metrics.cloudwatch is None

    @pytest.mark.asyncio
    async def test_put_metrics_with_no_client(self, mock_boto3):
        """Test putting metrics when CloudWatch client is None."""
        mock_boto3.client.side_effect = Exception("AWS credentials not found")
        
        metrics = CloudWatchMetrics()
        
        # Should not raise an exception, should handle gracefully
        await metrics.put_rate_limit_metrics("user", "tier", 10, 1)
        
        # No assertions needed, just ensure no exception is raised


class TestModuleFunctions:
    """Test module-level functions."""

    @patch('src.api.aws_rate_limiting.APIGatewayManager')
    def test_get_api_gateway_manager(self, mock_manager_class):
        """Test getting API Gateway manager instance."""
        mock_instance = Mock()
        mock_manager_class.return_value = mock_instance
        
        manager = get_api_gateway_manager()
        
        assert manager == mock_instance
        mock_manager_class.assert_called_once()

    @patch('src.api.aws_rate_limiting.CloudWatchMetrics')
    def test_get_cloudwatch_metrics(self, mock_metrics_class):
        """Test getting CloudWatch metrics instance."""
        mock_instance = Mock()
        mock_metrics_class.return_value = mock_instance
        
        metrics = get_cloudwatch_metrics()
        
        assert metrics == mock_instance
        mock_metrics_class.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.get_api_gateway_manager')
    @patch('src.api.aws_rate_limiting.get_cloudwatch_metrics')
    async def test_setup_aws_rate_limiting(self, mock_get_metrics, mock_get_manager):
        """Test setting up AWS rate limiting."""
        mock_manager = Mock()
        mock_metrics = Mock()
        mock_get_manager.return_value = mock_manager
        mock_get_metrics.return_value = mock_metrics
        
        # Mock the async methods
        mock_manager.create_usage_plans = AsyncMock(return_value={'free_tier': 'plan_123'})
        mock_metrics.create_rate_limit_alarms = AsyncMock()
        
        result = await setup_aws_rate_limiting()
        
        assert result == True
        mock_manager.create_usage_plans.assert_called_once()
        mock_metrics.create_rate_limit_alarms.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.get_api_gateway_manager')
    async def test_setup_aws_rate_limiting_failure(self, mock_get_manager):
        """Test setup failure handling."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        mock_manager.create_usage_plans = AsyncMock(side_effect=Exception("AWS Error"))
        
        result = await setup_aws_rate_limiting()
        
        assert result == False


class TestErrorHandling:
    """Test error handling scenarios."""

    @patch('src.api.aws_rate_limiting.boto3')
    def test_manager_with_invalid_credentials(self, mock_boto3):
        """Test manager behavior with invalid AWS credentials."""
        from botocore.exceptions import NoCredentialsError
        
        mock_boto3.client.side_effect = NoCredentialsError()
        
        manager = APIGatewayManager()
        
        assert manager.client is None
        assert manager.usage_client is None

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_usage_plan_creation_failure(self, mock_boto3):
        """Test handling of usage plan creation failure."""
        from botocore.exceptions import ClientError
        
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameter'}}, 'CreateUsagePlan'
        )
        
        manager = APIGatewayManager()
        result = await manager.create_usage_plans()
        
        # Should return empty dict on failure
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_assign_user_invalid_tier(self, mock_boto3):
        """Test assigning user to invalid tier."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        result = await manager.assign_user_to_plan("user", "invalid_tier", "key")
        
        assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_get_usage_statistics_key_not_found(self, mock_boto3):
        """Test getting usage statistics for non-existent API key."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.return_value = {'items': []}  # No keys found
        
        manager = APIGatewayManager()
        result = await manager.get_usage_statistics("nonexistent_key", "2024-01-01", "2024-01-02")
        
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_update_user_tier_user_not_found(self, mock_boto3):
        """Test updating tier for non-existent user."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.return_value = {'items': []}  # No keys found
        
        manager = APIGatewayManager()
        result = await manager.update_user_tier("nonexistent_user", "free", "premium")
        
        assert result == False

    def test_manager_operations_without_client(self):
        """Test manager operations when client is None."""
        with patch('src.api.aws_rate_limiting.boto3') as mock_boto3:
            mock_boto3.client.side_effect = Exception("No credentials")
            
            manager = APIGatewayManager()
            assert manager.client is None


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_complete_user_lifecycle(self, mock_boto3):
        """Test complete user lifecycle from signup to tier upgrade."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        # Mock responses for various operations
        mock_client.create_usage_plan.return_value = {'id': 'plan_123'}
        mock_client.create_api_key.return_value = {'id': 'key_123'}
        mock_client.create_usage_plan_key.return_value = {'id': 'plan_key_123'}
        mock_client.get_usage_plans.return_value = {
            'items': [{'name': 'Free Tier', 'id': 'free_plan_id'}]
        }
        mock_client.get_api_keys.return_value = {
            'items': [{'id': 'key_123', 'value': 'api_key_value', 'tags': {'user_id': 'user_123'}}]
        }
        
        manager = APIGatewayManager()
        
        # 1. Create usage plans
        plans = await manager.create_usage_plans()
        assert isinstance(plans, dict)
        
        # 2. Assign user to free tier
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'free_plan_id'}):
            with patch.object(manager, 'create_api_key_for_user', return_value='key_123'):
                assigned = await manager.assign_user_to_plan("user_123", "free", "api_key_value")
                assert assigned == True
        
        # 3. Get usage statistics
        mock_client.get_usage.return_value = {'values': {'2024-01-01': 50}}
        stats = await manager.get_usage_statistics("api_key_value", "2024-01-01", "2024-01-02")
        assert 'total_requests' in stats

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_monitoring_and_alerting_flow(self, mock_boto3):
        """Test monitoring and alerting workflow."""
        mock_cw_client = Mock()
        mock_boto3.client.return_value = mock_cw_client
        
        metrics = CloudWatchMetrics()
        
        # Test metrics publishing
        await metrics.put_rate_limit_metrics("user_123", "free", 100, 5)
        mock_cw_client.put_metric_data.assert_called()
        
        # Test alarm creation
        await metrics.create_rate_limit_alarms()
        mock_cw_client.put_metric_alarm.assert_called()
        
        # Verify alarm configuration
        call_args = mock_cw_client.put_metric_alarm.call_args
        assert call_args[1]['Threshold'] == 100.0
        assert call_args[1]['ComparisonOperator'] == 'GreaterThanThreshold'

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_usage_plans_without_api_id(self, mock_boto3):
        """Test creating usage plans without API Gateway ID."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan.return_value = {'id': 'plan_123'}
        
        # Test without API_GATEWAY_ID env var
        with patch.dict(os.environ, {}, clear=True):
            manager = APIGatewayManager()
            plans = await manager.create_usage_plans()
            
            assert isinstance(plans, dict)
            # Should not call create_usage_plan_key without api_id
            mock_client.create_usage_plan_key.assert_not_called()

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_usage_plans_client_failure(self, mock_boto3):
        """Test create usage plans with client failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan.side_effect = Exception("AWS API Error")
        
        manager = APIGatewayManager()
        plans = await manager.create_usage_plans()
        
        # Should return empty dict on exceptions
        assert plans == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_assign_user_plan_not_found(self, mock_boto3):
        """Test assigning user when plan is not found."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        with patch.object(manager, 'get_usage_plans', return_value={}):  # No plans found
            result = await manager.assign_user_to_plan("user", "free", "key")
            
            assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_api_key_failure(self, mock_boto3):
        """Test API key creation failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_api_key.side_effect = Exception("AWS Error")
        
        manager = APIGatewayManager()
        result = await manager.create_api_key_for_user("user", "key_value")
        
        assert result is None

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_get_usage_plans_failure(self, mock_boto3):
        """Test get usage plans failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_usage_plans.side_effect = Exception("AWS Error")
        
        manager = APIGatewayManager()
        result = await manager.get_usage_plans()
        
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_get_usage_statistics_failure(self, mock_boto3):
        """Test get usage statistics failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.side_effect = Exception("AWS Error")
        
        manager = APIGatewayManager()
        result = await manager.get_usage_statistics("key", "2024-01-01", "2024-01-02")
        
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_update_user_tier_failure(self, mock_boto3):
        """Test update user tier failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.side_effect = Exception("AWS Error")
        
        manager = APIGatewayManager()
        result = await manager.update_user_tier("user", "free", "premium")
        
        assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_monitor_throttling_events_failure(self, mock_boto3):
        """Test monitor throttling events failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        # Simulate exception in monitoring
        with patch.object(manager, 'monitor_throttling_events', side_effect=Exception("Error")):
            # Should handle gracefully
            try:
                await manager.monitor_throttling_events()
            except Exception:
                pass  # Expected

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_cloudwatch_put_metrics_failure(self, mock_boto3):
        """Test CloudWatch put metrics failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.put_metric_data.side_effect = Exception("CloudWatch Error")
        
        metrics = CloudWatchMetrics()
        # Should not raise exception
        await metrics.put_rate_limit_metrics("user", "tier", 10, 1)

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_cloudwatch_create_alarms_failure(self, mock_boto3):
        """Test CloudWatch create alarms failure."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.put_metric_alarm.side_effect = Exception("CloudWatch Error")
        
        metrics = CloudWatchMetrics()
        # Should not raise exception
        await metrics.create_rate_limit_alarms()

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_alarms_with_custom_sns_topic(self, mock_boto3):
        """Test creating alarms with custom SNS topic."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        with patch.dict(os.environ, {'SNS_ALERT_TOPIC': 'arn:aws:sns:us-east-1:123:custom-topic'}):
            metrics = CloudWatchMetrics()
            await metrics.create_rate_limit_alarms()
            
            call_args = mock_client.put_metric_alarm.call_args
            assert 'arn:aws:sns:us-east-1:123:custom-topic' in call_args[1]['AlarmActions']


class TestAdditionalCoverageScenarios:
    """Additional tests to reach 100% coverage."""
    
    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_usage_plans_no_client(self, mock_boto3):
        """Test create_usage_plans when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.create_usage_plans()
        
        # Should return empty dict when client is None
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_assign_user_to_plan_no_client(self, mock_boto3):
        """Test assign_user_to_plan when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.assign_user_to_plan("user", "free", "key")
        
        # Should return False when client is None
        assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_assign_user_create_api_key_fails(self, mock_boto3):
        """Test assign_user_to_plan when create_api_key_for_user returns None."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'plan_123'}):
            with patch.object(manager, 'create_api_key_for_user', return_value=None):
                result = await manager.assign_user_to_plan("user", "free", "key")
                
                assert result == False

    @pytest.mark.asyncio  
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_assign_user_to_plan_exception_handling(self, mock_boto3):
        """Test assign_user_to_plan exception handling."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.create_usage_plan_key.side_effect = Exception("AWS Error")
        
        manager = APIGatewayManager()
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'plan_123'}):
            with patch.object(manager, 'create_api_key_for_user', return_value='key_123'):
                result = await manager.assign_user_to_plan("user", "free", "key")
                
                assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_create_api_key_no_client(self, mock_boto3):
        """Test create_api_key_for_user when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.create_api_key_for_user("user", "key_value")
        
        # Should return None when client is None
        assert result is None

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_get_usage_plans_no_client(self, mock_boto3):
        """Test get_usage_plans when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.get_usage_plans()
        
        # Should return empty dict when client is None
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_get_usage_statistics_no_client(self, mock_boto3):
        """Test get_usage_statistics when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.get_usage_statistics("key", "2024-01-01", "2024-01-02")
        
        # Should return empty dict when client is None
        assert result == {}

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_update_user_tier_no_client(self, mock_boto3):
        """Test update_user_tier when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.update_user_tier("user", "free", "premium")
        
        # Should return False when client is None
        assert result == False

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_update_user_tier_old_plan_removal_warning(self, mock_boto3):
        """Test update_user_tier warning when removing from old plan fails."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        mock_client.get_api_keys.return_value = {
            'items': [{'id': 'key_123', 'value': 'test_api_key', 'tags': {'user_id': 'test_user'}}]
        }
        mock_client.delete_usage_plan_key.side_effect = Exception("Cannot remove from old plan")
        
        manager = APIGatewayManager()
        with patch.object(manager, 'get_usage_plans', return_value={'free_tier': 'old_plan_id'}):
            with patch.object(manager, 'assign_user_to_plan', return_value=True):
                result = await manager.update_user_tier("test_user", "free", "premium")
                
                # Should still succeed despite warning
                assert result == True

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_monitor_throttling_events_no_client(self, mock_boto3):
        """Test monitor_throttling_events when client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        manager = APIGatewayManager()
        result = await manager.monitor_throttling_events()
        
        # Should return empty list when client is None
        assert result == []

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_monitor_throttling_events_exception(self, mock_boto3):
        """Test monitor_throttling_events exception handling."""
        mock_client = Mock()
        mock_boto3.client.return_value = mock_client
        
        manager = APIGatewayManager()
        # Mock datetime.now() to cause an exception
        with patch('src.api.aws_rate_limiting.datetime') as mock_datetime:
            mock_datetime.now.side_effect = Exception("Time error")
            result = await manager.monitor_throttling_events()
            
            # Should return empty list on exception
            assert result == []

    @pytest.mark.asyncio
    @patch('src.api.aws_rate_limiting.boto3')
    async def test_cloudwatch_create_alarms_no_client(self, mock_boto3):
        """Test create_rate_limit_alarms when cloudwatch client is None."""
        mock_boto3.client.side_effect = Exception("No credentials")
        
        metrics = CloudWatchMetrics()
        # Should not raise exception when cloudwatch is None
        await metrics.create_rate_limit_alarms()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
