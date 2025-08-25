"""
Unit tests for MLflow tracking helper.

Tests the mlrun context manager and standardized tagging functionality.
"""

import os
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock
import mlflow
from mlflow.tracking import MlflowClient

from services.mlops.tracking import mlrun, _get_git_info, _get_environment, _get_code_version, setup_mlflow_env


class TestGitInfo:
    """Test git information extraction."""
    
    @patch('subprocess.run')
    def test_get_git_info_success(self, mock_run):
        """Test successful git info extraction."""
        # Mock git commands
        mock_run.side_effect = [
            MagicMock(stdout="abc123def456\n", returncode=0),  # git rev-parse HEAD
            MagicMock(stdout="feature-branch\n", returncode=0)  # git rev-parse --abbrev-ref HEAD
        ]
        
        git_info = _get_git_info()
        
        assert git_info["sha"] == "abc123def456"
        assert git_info["branch"] == "feature-branch"
    
    @patch('subprocess.run')
    def test_get_git_info_failure(self, mock_run):
        """Test git info extraction when git commands fail."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "git")
        
        git_info = _get_git_info()
        
        assert git_info["sha"] == "unknown"
        assert git_info["branch"] == "unknown"


class TestEnvironmentDetection:
    """Test environment detection logic."""
    
    def test_ci_environment_github_actions(self):
        """Test CI environment detection for GitHub Actions."""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert _get_environment() == "ci"
    
    def test_ci_environment_generic_ci(self):
        """Test CI environment detection for generic CI."""
        with patch.dict(os.environ, {"CI": "true"}):
            assert _get_environment() == "ci"
    
    def test_prod_environment(self):
        """Test production environment detection."""
        with patch.dict(os.environ, {"ENV": "production"}):
            assert _get_environment() == "prod"
    
    def test_dev_environment_default(self):
        """Test default development environment."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            assert _get_environment() == "dev"


class TestCodeVersion:
    """Test code version generation."""
    
    @patch('services.mlops.tracking._get_git_info')
    def test_code_version_with_git(self, mock_git_info):
        """Test code version from git SHA."""
        mock_git_info.return_value = {"sha": "abc123def456", "branch": "main"}
        
        version = _get_code_version()
        
        assert version == "abc123de"  # First 8 characters
    
    @patch('services.mlops.tracking._get_git_info')
    @patch('time.time')
    def test_code_version_without_git(self, mock_time, mock_git_info):
        """Test code version fallback without git."""
        mock_git_info.return_value = {"sha": "unknown", "branch": "unknown"}
        mock_time.return_value = 1234567890
        
        version = _get_code_version()
        
        assert version == "local-1234567890"


class TestMlrunContextManager:
    """Test the mlrun context manager."""
    
    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory for MLflow artifacts
        self.temp_dir = tempfile.mkdtemp()
        self.tracking_uri = f"file://{self.temp_dir}/mlruns"
        
        # Setup MLflow with file store
        mlflow.set_tracking_uri(self.tracking_uri)
    
    def teardown_method(self):
        """Cleanup test environment."""
        # Cleanup temporary directory
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        
        # End any active MLflow run
        if mlflow.active_run():
            mlflow.end_run()
    
    @patch('services.mlops.tracking._get_git_info')
    @patch('socket.gethostname')
    def test_mlrun_basic_functionality(self, mock_hostname, mock_git_info):
        """Test basic mlrun functionality with file store."""
        # Mock dependencies
        mock_git_info.return_value = {"sha": "test123", "branch": "test-branch"}
        mock_hostname.return_value = "test-host"
        
        # Test mlrun context manager
        with mlrun("test-run", experiment="test-experiment") as run:
            # Log test data
            mlflow.log_param("test_param", "test_value")
            mlflow.log_metric("test_metric", 0.95)
            
            # Create a test artifact
            artifact_file = os.path.join(self.temp_dir, "test_artifact.txt")
            with open(artifact_file, "w") as f:
                f.write("test artifact content")
            mlflow.log_artifact(artifact_file)
            
            # Verify run info
            assert run.info.run_id is not None
            assert run.info.status == "RUNNING"
        
        # Verify run completed
        client = MlflowClient(tracking_uri=self.tracking_uri)
        
        # Get experiment
        experiment = client.get_experiment_by_name("test-experiment")
        assert experiment is not None
        
        # Get runs for the experiment
        runs = client.search_runs(experiment_ids=[experiment.experiment_id])
        assert len(runs) == 1
        
        run = runs[0]
        
        # Verify standard tags
        assert run.data.tags["git.sha"] == "test123"
        assert run.data.tags["git.branch"] == "test-branch"
        assert run.data.tags["hostname"] == "test-host"
        assert "env" in run.data.tags
        assert "code_version" in run.data.tags
        
        # Verify standard parameters
        assert run.data.params["run_name"] == "test-run"
        assert run.data.params["git_sha"] == "test123"
        assert run.data.params["git_branch"] == "test-branch"
        assert run.data.params["hostname"] == "test-host"
        
        # Verify logged data
        assert run.data.params["test_param"] == "test_value"
        assert "test_metric" in run.data.metrics
        assert run.data.metrics["test_metric"] == 0.95
        
        # Verify artifacts
        artifacts = client.list_artifacts(run.info.run_id)
        assert len(artifacts) > 0
        assert any(artifact.path == "test_artifact.txt" for artifact in artifacts)
    
    @patch('services.mlops.tracking._get_git_info')
    def test_mlrun_with_custom_tags(self, mock_git_info):
        """Test mlrun with custom tags."""
        mock_git_info.return_value = {"sha": "test123", "branch": "test-branch"}
        
        custom_tags = {
            "model_type": "bert",
            "data_version": "v1.2.3",
            "custom_tag": "custom_value"
        }
        
        with mlrun("test-run-custom", tags=custom_tags) as run:
            mlflow.log_param("test_param", "value")
        
        # Verify custom tags were added
        client = MlflowClient(tracking_uri=self.tracking_uri)
        experiments = client.search_experiments()
        runs = client.search_runs(experiment_ids=[exp.experiment_id for exp in experiments])
        
        latest_run = runs[0]  # Most recent run
        
        # Verify custom tags
        assert latest_run.data.tags["model_type"] == "bert"
        assert latest_run.data.tags["data_version"] == "v1.2.3"
        assert latest_run.data.tags["custom_tag"] == "custom_value"
        
        # Verify standard tags still present
        assert "git.sha" in latest_run.data.tags
        assert "env" in latest_run.data.tags
    
    @patch.dict(os.environ, {"NEURONEWS_PIPELINE": "sentiment-analyzer"})
    @patch('services.mlops.tracking._get_git_info')
    def test_mlrun_with_pipeline_tag(self, mock_git_info):
        """Test mlrun with pipeline tag from environment."""
        mock_git_info.return_value = {"sha": "test123", "branch": "test-branch"}
        
        with mlrun("pipeline-test") as run:
            mlflow.log_param("test", "value")
        
        # Verify pipeline tag
        client = MlflowClient(tracking_uri=self.tracking_uri)
        experiments = client.search_experiments()
        runs = client.search_runs(experiment_ids=[exp.experiment_id for exp in experiments])
        
        latest_run = runs[0]
        assert latest_run.data.tags["pipeline"] == "sentiment-analyzer"


class TestSetupHelpers:
    """Test setup helper functions."""
    
    def test_setup_mlflow_env(self):
        """Test MLflow environment setup."""
        test_uri = "http://test-server:5000"
        test_experiment = "test-exp"
        
        setup_mlflow_env(tracking_uri=test_uri, experiment=test_experiment)
        
        assert os.environ["MLFLOW_TRACKING_URI"] == test_uri
        assert os.environ["MLFLOW_EXPERIMENT"] == test_experiment


@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring MLflow server."""
    
    def test_mlrun_integration(self):
        """
        Integration test with real MLflow server.
        
        Note: This test requires MLflow server to be running on localhost:5001
        You can start it with: make mlflow-up
        """
        try:
            # Setup environment for local MLflow server
            setup_mlflow_env("http://localhost:5001", "test-integration")
            
            with mlrun("integration-test") as run:
                mlflow.log_param("integration", "true")
                mlflow.log_metric("test_score", 0.98)
            
            print(f"Integration test completed successfully. Run ID: {run.info.run_id}")
            
        except Exception as e:
            pytest.skip(f"MLflow server not available: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
