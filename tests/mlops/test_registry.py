"""
Unit tests for MLflow Model Registry implementation.

Tests the NeuroNewsModelRegistry class and related functionality
for model lifecycle management.
"""

import pytest
import tempfile
import shutil
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any

import mlflow
from mlflow.entities.model_registry import ModelVersion, RegisteredModel
from mlflow.exceptions import MlflowException

# Add project root to path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from services.mlops.registry import (
    NeuroNewsModelRegistry,
    ModelMetadata,
    ModelStage,
    ModelPerformanceGate,
    register_model_from_run,
    promote_to_production,
    get_production_model_uri,
    list_all_models
)


class TestModelPerformanceGate:
    """Test ModelPerformanceGate functionality."""
    
    def test_greater_than_check(self):
        gate = ModelPerformanceGate("accuracy", 0.8, "greater")
        assert gate.check(0.85) is True
        assert gate.check(0.75) is False
        assert gate.check(0.8) is False
    
    def test_less_than_check(self):
        gate = ModelPerformanceGate("latency", 100, "less")
        assert gate.check(90) is True
        assert gate.check(110) is False
        assert gate.check(100) is False
    
    def test_equal_check(self):
        gate = ModelPerformanceGate("target", 1.0, "equal")
        assert gate.check(1.0) is True
        assert gate.check(1.001) is False  # Outside tolerance
        assert gate.check(0.999) is True   # Within tolerance
    
    def test_invalid_comparison(self):
        gate = ModelPerformanceGate("metric", 0.5, "invalid")
        with pytest.raises(ValueError, match="Invalid comparison: invalid"):
            gate.check(0.6)


class TestModelMetadata:
    """Test ModelMetadata dataclass."""
    
    def test_model_metadata_creation(self):
        metadata = ModelMetadata(
            name="test_model",
            description="Test model description",
            tags={"team": "test"},
            owner="test-owner",
            use_case="testing",
            performance_metrics={"accuracy": 0.9},
            deployment_target="staging"
        )
        
        assert metadata.name == "test_model"
        assert metadata.description == "Test model description"
        assert metadata.tags == {"team": "test"}
        assert metadata.owner == "test-owner"
        assert metadata.use_case == "testing"
        assert metadata.performance_metrics == {"accuracy": 0.9}
        assert metadata.deployment_target == "staging"


class TestNeuroNewsModelRegistry:
    """Test NeuroNewsModelRegistry class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_client(self):
        """Mock MLflow client."""
        with patch('services.mlops.registry.MlflowClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def registry(self, mock_client, temp_dir):
        """Create registry instance with mocked client."""
        tracking_uri = f"file://{temp_dir}"
        with patch('mlflow.set_tracking_uri'):
            registry = NeuroNewsModelRegistry(tracking_uri)
            registry.client = mock_client
            return registry
    
    def test_initialization_with_tracking_uri(self, temp_dir):
        """Test registry initialization with tracking URI."""
        tracking_uri = f"file://{temp_dir}"
        
        with patch('mlflow.set_tracking_uri') as mock_set_uri:
            with patch('services.mlops.registry.MlflowClient'):
                registry = NeuroNewsModelRegistry(tracking_uri)
                mock_set_uri.assert_called_once_with(tracking_uri)
    
    def test_initialization_with_env_variable(self, temp_dir):
        """Test registry initialization with environment variable."""
        tracking_uri = f"file://{temp_dir}"
        
        with patch.dict(os.environ, {'MLFLOW_TRACKING_URI': tracking_uri}):
            with patch('mlflow.set_tracking_uri') as mock_set_uri:
                with patch('services.mlops.registry.MlflowClient'):
                    registry = NeuroNewsModelRegistry()
                    mock_set_uri.assert_called_once_with(tracking_uri)
    
    def test_initialization_default(self):
        """Test registry initialization with default settings."""
        with patch('mlflow.set_tracking_uri') as mock_set_uri:
            with patch('services.mlops.registry.MlflowClient'):
                registry = NeuroNewsModelRegistry()
                mock_set_uri.assert_called_once_with("file:./mlruns")
    
    def test_register_model_new_standard_model(self, registry, mock_client):
        """Test registering a new standard model."""
        # Mock model version
        mock_version = Mock()
        mock_version.version = "1"
        mock_version.name = "neuro_sentiment_classifier"
        
        # Mock that model doesn't exist
        mock_client.get_registered_model.side_effect = MlflowException("Model not found")
        mock_client.create_registered_model.return_value = Mock()
        mock_client.create_model_version.return_value = mock_version
        
        # Register model
        version = registry.register_model(
            model_uri="runs:/abc123/model",
            name="neuro_sentiment_classifier"
        )
        
        assert version.name == "neuro_sentiment_classifier"
        assert version.version == "1"
        mock_client.create_registered_model.assert_called_once()
        mock_client.create_model_version.assert_called_once()
    
    def test_register_model_existing_model(self, registry, mock_client):
        """Test registering version of existing model."""
        # Mock existing model
        mock_existing_model = Mock()
        mock_client.get_registered_model.return_value = mock_existing_model
        
        # Mock new version
        mock_version = Mock()
        mock_version.version = "2"
        mock_version.name = "neuro_sentiment_classifier"
        mock_client.create_model_version.return_value = mock_version
        
        # Register model
        version = registry.register_model(
            model_uri="runs:/def456/model",
            name="neuro_sentiment_classifier"
        )
        
        assert version.version == "2"
        mock_client.create_registered_model.assert_not_called()  # Should not create new
        mock_client.create_model_version.assert_called_once()
    
    def test_register_model_with_metadata(self, registry, mock_client):
        """Test registering model with comprehensive metadata."""
        metadata = ModelMetadata(
            name="neuro_sentiment_classifier",
            description="Test sentiment classifier",
            tags={"team": "nlp", "algorithm": "rf"},
            owner="test-team",
            use_case="sentiment_analysis",
            performance_metrics={"accuracy": 0.9, "f1": 0.85},
            deployment_target="production"
        )
        
        # Mock responses
        mock_client.get_registered_model.side_effect = MlflowException("Not found")
        mock_client.create_registered_model.return_value = Mock()
        
        mock_version = Mock()
        mock_version.version = "1"
        mock_client.create_model_version.return_value = mock_version
        
        # Register with metadata
        version = registry.register_model(
            model_uri="runs:/abc123/model",
            name="neuro_sentiment_classifier",
            metadata=metadata
        )
        
        # Verify registration called with tags
        call_args = mock_client.create_registered_model.call_args
        assert "tags" in call_args.kwargs
        tags = call_args.kwargs["tags"]
        assert tags["owner"] == "test-team"
        assert tags["project"] == "neuronews"
    
    def test_transition_model_stage_success(self, registry, mock_client):
        """Test successful stage transition."""
        mock_version = Mock()
        mock_version.version = "1"
        mock_version.current_stage = "Production"
        
        mock_client.transition_model_version_stage.return_value = mock_version
        
        # Mock performance gate check
        with patch.object(registry, '_check_performance_gates', return_value=True):
            result = registry.transition_model_stage(
                name="neuro_sentiment_classifier",
                version="1",
                stage=ModelStage.PRODUCTION
            )
        
        assert result.current_stage == "Production"
        mock_client.transition_model_version_stage.assert_called_once()
    
    def test_transition_model_stage_performance_gate_failure(self, registry, mock_client):
        """Test stage transition with performance gate failure."""
        # Mock performance gate failure
        with patch.object(registry, '_check_performance_gates', return_value=False):
            with pytest.raises(ValueError, match="does not meet performance gates"):
                registry.transition_model_stage(
                    name="neuro_sentiment_classifier",
                    version="1",
                    stage=ModelStage.PRODUCTION,
                    check_performance_gates=True
                )
    
    def test_get_model_versions_all(self, registry, mock_client):
        """Test getting all model versions."""
        mock_model = Mock()
        mock_model.latest_versions = [
            Mock(version="1", current_stage="Staging"),
            Mock(version="2", current_stage="Production")
        ]
        mock_client.get_registered_model.return_value = mock_model
        
        versions = registry.get_model_versions("test_model")
        
        assert len(versions) == 2
        assert versions[0].version == "1"
        assert versions[1].version == "2"
    
    def test_get_model_versions_filtered(self, registry, mock_client):
        """Test getting model versions filtered by stage."""
        mock_model = Mock()
        mock_model.latest_versions = [
            Mock(version="1", current_stage="Staging"),
            Mock(version="2", current_stage="Production"),
            Mock(version="3", current_stage="None")
        ]
        mock_client.get_registered_model.return_value = mock_model
        
        production_versions = registry.get_model_versions(
            "test_model", 
            [ModelStage.PRODUCTION]
        )
        
        assert len(production_versions) == 1
        assert production_versions[0].version == "2"
        assert production_versions[0].current_stage == "Production"
    
    def test_get_production_model(self, registry, mock_client):
        """Test getting production model version."""
        mock_model = Mock()
        mock_production_version = Mock(version="2", current_stage="Production")
        mock_model.latest_versions = [
            Mock(version="1", current_stage="Staging"),
            mock_production_version
        ]
        mock_client.get_registered_model.return_value = mock_model
        
        production_version = registry.get_production_model("test_model")
        
        assert production_version.version == "2"
        assert production_version.current_stage == "Production"
    
    def test_get_production_model_none(self, registry, mock_client):
        """Test getting production model when none exists."""
        mock_model = Mock()
        mock_model.latest_versions = [
            Mock(version="1", current_stage="Staging"),
            Mock(version="2", current_stage="None")
        ]
        mock_client.get_registered_model.return_value = mock_model
        
        production_version = registry.get_production_model("test_model")
        
        assert production_version is None
    
    def test_get_latest_model(self, registry, mock_client):
        """Test getting latest model version."""
        mock_model = Mock()
        mock_model.latest_versions = [
            Mock(version="1", current_stage="Staging"),
            Mock(version="3", current_stage="None"),  # Latest
            Mock(version="2", current_stage="Production")
        ]
        mock_client.get_registered_model.return_value = mock_model
        
        latest_version = registry.get_latest_model("test_model")
        
        assert latest_version.version == "3"  # Highest version number
    
    def test_compare_model_versions(self, registry, mock_client):
        """Test comparing two model versions."""
        # Mock model versions with different metrics
        mock_v1 = Mock()
        mock_v1.version = "1"
        mock_v1.current_stage = "Staging"
        mock_v1.creation_timestamp = 1000
        
        mock_v2 = Mock()
        mock_v2.version = "2"
        mock_v2.current_stage = "Production"
        mock_v2.creation_timestamp = 2000
        
        mock_client.get_model_version.side_effect = [mock_v1, mock_v2]
        
        # Mock metric extraction
        with patch.object(registry, '_extract_performance_metrics') as mock_extract:
            mock_extract.side_effect = [
                {"accuracy": 0.8, "f1": 0.75},  # v1 metrics
                {"accuracy": 0.85, "f1": 0.80}  # v2 metrics
            ]
            
            comparison = registry.compare_model_versions("test_model", "1", "2")
        
        assert comparison["model_name"] == "test_model"
        assert comparison["version1"]["version"] == "1"
        assert comparison["version2"]["version"] == "2"
        assert comparison["improvements"]["accuracy"]["relative_change"] == 6.25  # (0.85-0.8)/0.8 * 100
    
    def test_archive_old_versions(self, registry, mock_client):
        """Test archiving old model versions."""
        # Mock model with multiple versions
        mock_model = Mock()
        mock_model.latest_versions = [
            Mock(version="1", current_stage="None", creation_timestamp=1000),
            Mock(version="2", current_stage="Staging", creation_timestamp=2000),
            Mock(version="3", current_stage="Production", creation_timestamp=3000),
            Mock(version="4", current_stage="None", creation_timestamp=4000),
            Mock(version="5", current_stage="None", creation_timestamp=5000)  # Latest
        ]
        mock_client.get_registered_model.return_value = mock_model
        mock_client.transition_model_version_stage.return_value = Mock()
        
        archived = registry.archive_old_versions(
            name="test_model",
            keep_latest_n=2,
            exclude_production=True
        )
        
        # Should archive versions 1 and 2 (oldest, excluding production v3)
        assert "1" in archived
        assert "2" in archived
        assert len(archived) == 2
    
    def test_get_model_deployment_info(self, registry, mock_client):
        """Test getting model deployment information."""
        # Mock different model versions
        mock_production = Mock(version="2", creation_timestamp=2000)
        mock_staging = Mock(version="3", creation_timestamp=3000)
        mock_latest = Mock(version="4", current_stage="None")
        
        # Mock registry methods
        with patch.object(registry, 'get_production_model', return_value=mock_production):
            with patch.object(registry, 'get_model_versions', return_value=[mock_staging]):
                with patch.object(registry, 'get_latest_model', return_value=mock_latest):
                    
                    deployment_info = registry.get_model_deployment_info("test_model")
        
        assert deployment_info["model_name"] == "test_model"
        assert deployment_info["production"]["version"] == "2"
        assert deployment_info["production"]["model_uri"] == "models:/test_model/Production"
        assert len(deployment_info["staging"]) == 1
        assert deployment_info["staging"][0]["version"] == "3"
        assert deployment_info["latest"]["version"] == "4"
    
    def test_check_performance_gates_pass(self, registry, mock_client):
        """Test performance gates check that passes."""
        # Mock model version and run data
        mock_version = Mock()
        mock_version.run_id = "run123"
        mock_version.tags = {}
        
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.9, "f1_score": 0.85}
        
        mock_client.get_model_version.return_value = mock_version
        mock_client.get_run.return_value = mock_run
        
        # Test sentiment classifier gates (accuracy > 0.85, f1_score > 0.80)
        result = registry._check_performance_gates("neuro_sentiment_classifier", "1")
        
        assert result is True
    
    def test_check_performance_gates_fail(self, registry, mock_client):
        """Test performance gates check that fails."""
        # Mock model version and run data with poor performance
        mock_version = Mock()
        mock_version.run_id = "run123"
        mock_version.tags = {}
        
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.7, "f1_score": 0.75}  # Below thresholds
        
        mock_client.get_model_version.return_value = mock_version
        mock_client.get_run.return_value = mock_run
        
        # Test sentiment classifier gates
        result = registry._check_performance_gates("neuro_sentiment_classifier", "1")
        
        assert result is False
    
    def test_extract_performance_metrics_from_run(self, registry, mock_client):
        """Test extracting performance metrics from MLflow run."""
        mock_version = Mock()
        mock_version.run_id = "run123"
        mock_version.tags = {}
        
        mock_run = Mock()
        mock_run.data.metrics = {"accuracy": 0.9, "f1_score": 0.85, "precision": 0.88}
        
        mock_client.get_run.return_value = mock_run
        
        metrics = registry._extract_performance_metrics(mock_version)
        
        assert metrics["accuracy"] == 0.9
        assert metrics["f1_score"] == 0.85
        assert metrics["precision"] == 0.88
    
    def test_extract_performance_metrics_from_tags(self, registry, mock_client):
        """Test extracting performance metrics from model version tags."""
        mock_version = Mock()
        mock_version.run_id = None  # No run ID
        mock_version.tags = {
            "performance_metrics": "{'accuracy': 0.92, 'f1_score': 0.89}"
        }
        
        metrics = registry._extract_performance_metrics(mock_version)
        
        assert metrics["accuracy"] == 0.92
        assert metrics["f1_score"] == 0.89


class TestHelperFunctions:
    """Test module-level helper functions."""
    
    @patch('services.mlops.registry.NeuroNewsModelRegistry')
    def test_register_model_from_run(self, mock_registry_class):
        """Test register_model_from_run helper function."""
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry
        
        mock_version = Mock()
        mock_registry.register_model.return_value = mock_version
        
        # Test function
        result = register_model_from_run(
            run_id="run123",
            model_name="test_model"
        )
        
        assert result == mock_version
        mock_registry.register_model.assert_called_once_with(
            model_uri="runs:/run123/model",
            name="test_model",
            metadata=None
        )
    
    @patch('services.mlops.registry.NeuroNewsModelRegistry')
    def test_promote_to_production(self, mock_registry_class):
        """Test promote_to_production helper function."""
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry
        
        mock_version = Mock()
        mock_registry.transition_model_stage.return_value = mock_version
        
        # Test function
        result = promote_to_production("test_model", "1")
        
        assert result == mock_version
        mock_registry.transition_model_stage.assert_called_once_with(
            name="test_model",
            version="1",
            stage=ModelStage.PRODUCTION,
            description="Promoted to production based on validation results",
            check_performance_gates=True
        )
    
    @patch('services.mlops.registry.NeuroNewsModelRegistry')
    def test_get_production_model_uri(self, mock_registry_class):
        """Test get_production_model_uri helper function."""
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry
        
        mock_version = Mock()
        mock_registry.get_production_model.return_value = mock_version
        
        # Test function
        result = get_production_model_uri("test_model")
        
        assert result == "models:/test_model/Production"
    
    @patch('services.mlops.registry.NeuroNewsModelRegistry')
    def test_get_production_model_uri_none(self, mock_registry_class):
        """Test get_production_model_uri when no production model exists."""
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry
        
        mock_registry.get_production_model.return_value = None
        
        # Test function
        result = get_production_model_uri("test_model")
        
        assert result is None
    
    @patch('services.mlops.registry.NeuroNewsModelRegistry')
    def test_list_all_models(self, mock_registry_class):
        """Test list_all_models helper function."""
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry
        
        # Mock registered models
        mock_model1 = Mock()
        mock_model1.name = "model1"
        mock_model1.description = "Test model 1"
        mock_model1.creation_timestamp = 1000
        mock_model1.last_updated_timestamp = 2000
        mock_model1.latest_versions = [Mock(version="1", current_stage="Production")]
        mock_model1.tags = {"team": "test"}
        
        mock_registry.client.list_registered_models.return_value = [mock_model1]
        
        # Test function
        result = list_all_models()
        
        assert "model1" in result
        assert result["model1"]["description"] == "Test model 1"
        assert len(result["model1"]["latest_versions"]) == 1


if __name__ == "__main__":
    pytest.main([__file__])
