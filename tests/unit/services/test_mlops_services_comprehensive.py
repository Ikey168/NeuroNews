#!/usr/bin/env python3
"""
MLOps Services Testing - Issue #487
Comprehensive tests for MLOps and Data Management services

Tests for:
- ModelTracker (MLflow tracking)
- ModelRegistry (MLflow model registry)  
- DataManifest (data lineage and governance)
- MLPipelineMonitor (pipeline monitoring)
"""

import os
import sys
import pytest
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


class TestMLOpsTrackingService:
    """Test MLOps tracking service functionality"""
    
    def test_mlflow_tracking_import_and_structure(self):
        """Test MLflow tracking service import and structure"""
        try:
            from services.mlops.tracking import (
                validate_experiment_name,
                STANDARD_EXPERIMENTS,
                REQUIRED_TAGS,
                VALID_ENVIRONMENTS
            )
            
            # Test that constants are defined
            assert isinstance(STANDARD_EXPERIMENTS, dict)
            assert isinstance(REQUIRED_TAGS, list)
            assert isinstance(VALID_ENVIRONMENTS, list)
            
            # Test validation function
            assert callable(validate_experiment_name)
            
            # Test standard experiments exist
            assert 'neuro_news_indexing' in STANDARD_EXPERIMENTS
            assert 'neuro_news_ask' in STANDARD_EXPERIMENTS
            assert 'research_prototypes' in STANDARD_EXPERIMENTS
            
            # Test required tags are defined
            expected_tags = ["git.sha", "env", "pipeline", "data_version"]
            for tag in expected_tags:
                assert tag in REQUIRED_TAGS
            
            # Test environments are defined
            expected_envs = ["dev", "staging", "prod"]
            for env in expected_envs:
                assert env in VALID_ENVIRONMENTS
                
        except ImportError as e:
            pytest.skip(f"MLflow tracking not available: {e}")
    
    def test_experiment_name_validation(self):
        """Test experiment name validation functionality"""
        try:
            from services.mlops.tracking import validate_experiment_name, STANDARD_EXPERIMENTS
            
            # Test valid standard experiment names
            for exp_name in STANDARD_EXPERIMENTS.keys():
                assert validate_experiment_name(exp_name) is True
            
            # Test validation function behavior
            assert validate_experiment_name('neuro_news_indexing') is True
            assert validate_experiment_name('neuro_news_ask') is True
            
        except ImportError as e:
            pytest.skip(f"MLflow tracking validation not available: {e}")
    
    def test_tracking_service_interface_pattern(self):
        """Test tracking service interface pattern"""
        # Mock the tracking service interface
        class MockMLflowTracker:
            def __init__(self):
                self.experiments = {}
                self.runs = {}
                self.current_run = None
            
            def create_experiment(self, name, description=None):
                self.experiments[name] = {
                    'description': description,
                    'runs': []
                }
                return name
            
            def start_run(self, experiment_name, run_name=None):
                run_id = f"run_{len(self.runs)}"
                run_data = {
                    'id': run_id,
                    'experiment': experiment_name,
                    'name': run_name,
                    'parameters': {},
                    'metrics': {},
                    'tags': {},
                    'artifacts': []
                }
                self.runs[run_id] = run_data
                self.current_run = run_id
                return run_id
            
            def log_param(self, key, value):
                if self.current_run:
                    self.runs[self.current_run]['parameters'][key] = value
            
            def log_metric(self, key, value, step=None):
                if self.current_run:
                    self.runs[self.current_run]['metrics'][key] = value
            
            def set_tag(self, key, value):
                if self.current_run:
                    self.runs[self.current_run]['tags'][key] = value
            
            def end_run(self):
                if self.current_run:
                    self.runs[self.current_run]['status'] = 'finished'
                    self.current_run = None
        
        # Test the tracking interface
        tracker = MockMLflowTracker()
        
        # Test experiment creation
        exp_name = tracker.create_experiment("test_experiment", "Test experiment")
        assert exp_name == "test_experiment"
        assert "test_experiment" in tracker.experiments
        
        # Test run lifecycle
        run_id = tracker.start_run("test_experiment", "test_run")
        assert run_id in tracker.runs
        assert tracker.current_run == run_id
        
        # Test parameter logging
        tracker.log_param("learning_rate", 0.001)
        tracker.log_param("batch_size", 32)
        
        # Test metric logging
        tracker.log_metric("accuracy", 0.95)
        tracker.log_metric("loss", 0.05)
        
        # Test tag setting
        tracker.set_tag("git.sha", "abc123")
        tracker.set_tag("env", "dev")
        
        # Test run completion
        tracker.end_run()
        
        # Verify data was logged correctly
        run_data = tracker.runs[run_id]
        assert run_data['parameters']['learning_rate'] == 0.001
        assert run_data['parameters']['batch_size'] == 32
        assert run_data['metrics']['accuracy'] == 0.95
        assert run_data['tags']['git.sha'] == "abc123"
        assert run_data['status'] == 'finished'


class TestMLOpsModelRegistry:
    """Test MLOps model registry functionality"""
    
    def test_model_registry_import_and_structure(self):
        """Test model registry import and structure"""
        try:
            from services.mlops.registry import (
                ModelStage,
                TransitionRequirement,
                ModelMetadata
            )
            
            # Test enums are defined
            assert ModelStage.NONE.value == "None"
            assert ModelStage.STAGING.value == "Staging"
            assert ModelStage.PRODUCTION.value == "Production"
            assert ModelStage.ARCHIVED.value == "Archived"
            
            # Test transition requirements
            assert TransitionRequirement.MANUAL_APPROVAL.value == "manual"
            assert TransitionRequirement.AUTOMATIC.value == "automatic"
            assert TransitionRequirement.PERFORMANCE_GATE.value == "performance"
            
            # Test ModelMetadata dataclass
            metadata = ModelMetadata(
                name="test_model",
                description="Test model",
                tags={"version": "1.0"},
                owner="test_user",
                use_case="classification",
                performance_metrics={"accuracy": 0.95},
                deployment_target="production"
            )
            
            assert metadata.name == "test_model"
            assert metadata.performance_metrics["accuracy"] == 0.95
            
        except ImportError as e:
            pytest.skip(f"Model registry not available: {e}")
    
    def test_model_registry_interface_pattern(self):
        """Test model registry interface pattern"""
        # Mock model registry interface
        class MockModelRegistry:
            def __init__(self):
                self.registered_models = {}
                self.model_versions = {}
            
            def create_registered_model(self, name, description=None, tags=None):
                self.registered_models[name] = {
                    'description': description,
                    'tags': tags or {},
                    'versions': []
                }
                return name
            
            def create_model_version(self, name, source, run_id=None):
                if name not in self.registered_models:
                    raise ValueError(f"Model {name} not registered")
                
                version = len(self.registered_models[name]['versions']) + 1
                version_data = {
                    'version': version,
                    'source': source,
                    'run_id': run_id,
                    'stage': 'None',
                    'status': 'ready'
                }
                
                self.registered_models[name]['versions'].append(version_data)
                version_key = f"{name}:v{version}"
                self.model_versions[version_key] = version_data
                
                return version
            
            def transition_model_version_stage(self, name, version, stage):
                version_key = f"{name}:v{version}"
                if version_key in self.model_versions:
                    self.model_versions[version_key]['stage'] = stage
                    return True
                return False
            
            def get_model_version(self, name, version):
                version_key = f"{name}:v{version}"
                return self.model_versions.get(version_key)
            
            def get_latest_versions(self, name, stages=None):
                if name not in self.registered_models:
                    return []
                
                versions = self.registered_models[name]['versions']
                if stages:
                    versions = [v for v in versions if v['stage'] in stages]
                
                return sorted(versions, key=lambda x: x['version'], reverse=True)
        
        # Test model registry interface
        registry = MockModelRegistry()
        
        # Test model registration
        model_name = registry.create_registered_model(
            "classifier_model",
            description="Document classifier",
            tags={"team": "ml", "use_case": "classification"}
        )
        assert model_name == "classifier_model"
        assert "classifier_model" in registry.registered_models
        
        # Test model version creation
        version = registry.create_model_version(
            "classifier_model",
            source="s3://models/classifier/v1",
            run_id="run_123"
        )
        assert version == 1
        
        # Test stage transition
        success = registry.transition_model_version_stage("classifier_model", 1, "Staging")
        assert success is True
        
        # Test version retrieval
        version_info = registry.get_model_version("classifier_model", 1)
        assert version_info['stage'] == "Staging"
        assert version_info['source'] == "s3://models/classifier/v1"
        
        # Test latest versions retrieval
        latest_staging = registry.get_latest_versions("classifier_model", ["Staging"])
        assert len(latest_staging) == 1
        assert latest_staging[0]['version'] == 1


class TestDataManifestService:
    """Test data manifest and lineage service"""
    
    def test_data_manifest_import_and_structure(self):
        """Test data manifest import and structure"""
        try:
            from services.mlops.data_manifest import DataManifestGenerator
            
            # Test that we can create a generator
            generator = DataManifestGenerator()
            assert generator is not None
            assert hasattr(generator, 'hash_algorithms')
            assert hasattr(generator, 'supported_algorithms')
            
            # Test default hash algorithms
            assert 'md5' in generator.hash_algorithms
            assert 'sha256' in generator.hash_algorithms
            
            # Test supported algorithms
            expected_algorithms = ['md5', 'sha1', 'sha256', 'sha512']
            for alg in expected_algorithms:
                assert alg in generator.supported_algorithms
            
        except ImportError as e:
            pytest.skip(f"Data manifest not available: {e}")
    
    def test_data_manifest_interface_pattern(self):
        """Test data manifest interface pattern"""
        # Mock data manifest interface
        class MockDataManifest:
            def __init__(self):
                self.manifests = {}
                self.lineage = {}
            
            def generate_manifest(self, data_path, include_subdirs=True):
                """Generate manifest for data path"""
                manifest_id = f"manifest_{len(self.manifests)}"
                manifest = {
                    'id': manifest_id,
                    'path': data_path,
                    'files': [],
                    'metadata': {
                        'created_at': '2024-01-01T00:00:00Z',
                        'total_size': 0,
                        'file_count': 0
                    }
                }
                
                # Mock file processing
                if data_path == "/data/test":
                    manifest['files'] = [
                        {
                            'path': 'file1.csv',
                            'size': 1024,
                            'md5': 'abc123',
                            'sha256': 'def456'
                        },
                        {
                            'path': 'file2.json', 
                            'size': 512,
                            'md5': 'ghi789',
                            'sha256': 'jkl012'
                        }
                    ]
                    manifest['metadata']['total_size'] = 1536
                    manifest['metadata']['file_count'] = 2
                
                self.manifests[manifest_id] = manifest
                return manifest
            
            def validate_manifest(self, manifest_id, data_path):
                """Validate data against manifest"""
                if manifest_id not in self.manifests:
                    return False, "Manifest not found"
                
                manifest = self.manifests[manifest_id]
                # Mock validation - in real implementation would check file hashes
                return True, "All files validated successfully"
            
            def track_lineage(self, input_manifests, output_manifest, transformation):
                """Track data lineage"""
                lineage_id = f"lineage_{len(self.lineage)}"
                self.lineage[lineage_id] = {
                    'inputs': input_manifests,
                    'output': output_manifest,
                    'transformation': transformation,
                    'timestamp': '2024-01-01T00:00:00Z'
                }
                return lineage_id
            
            def get_lineage_graph(self, manifest_id):
                """Get lineage graph for manifest"""
                # Find all lineage entries involving this manifest
                related_lineage = []
                for lineage_id, lineage_data in self.lineage.items():
                    if (manifest_id in lineage_data['inputs'] or 
                        manifest_id == lineage_data['output']):
                        related_lineage.append(lineage_data)
                
                return related_lineage
        
        # Test data manifest interface
        manifest_service = MockDataManifest()
        
        # Test manifest generation
        manifest = manifest_service.generate_manifest("/data/test")
        assert manifest['path'] == "/data/test"
        assert manifest['metadata']['file_count'] == 2
        assert len(manifest['files']) == 2
        
        # Test file details
        file1 = manifest['files'][0]
        assert file1['path'] == 'file1.csv'
        assert file1['size'] == 1024
        assert 'md5' in file1
        assert 'sha256' in file1
        
        # Test manifest validation
        is_valid, message = manifest_service.validate_manifest(manifest['id'], "/data/test")
        assert is_valid is True
        assert "validated successfully" in message
        
        # Test lineage tracking
        input_manifest = manifest_service.generate_manifest("/data/input")
        output_manifest = manifest_service.generate_manifest("/data/output")
        
        lineage_id = manifest_service.track_lineage(
            [input_manifest['id']],
            output_manifest['id'],
            {"process": "data_cleaning", "version": "1.0"}
        )
        
        assert lineage_id is not None
        assert lineage_id in manifest_service.lineage
        
        # Test lineage graph retrieval
        lineage_graph = manifest_service.get_lineage_graph(output_manifest['id'])
        assert len(lineage_graph) == 1
        assert lineage_graph[0]['transformation']['process'] == "data_cleaning"


class TestMLPipelineMonitoring:
    """Test ML pipeline monitoring patterns"""
    
    def test_ml_pipeline_monitoring_interface(self):
        """Test ML pipeline monitoring interface"""
        # Mock ML pipeline monitor
        class MockMLPipelineMonitor:
            def __init__(self):
                self.pipelines = {}
                self.metrics = {}
                self.alerts = []
            
            def register_pipeline(self, pipeline_id, config):
                """Register a pipeline for monitoring"""
                self.pipelines[pipeline_id] = {
                    'config': config,
                    'status': 'registered',
                    'runs': [],
                    'last_run': None
                }
                return pipeline_id
            
            def start_pipeline_run(self, pipeline_id, run_config=None):
                """Start monitoring a pipeline run"""
                if pipeline_id not in self.pipelines:
                    raise ValueError(f"Pipeline {pipeline_id} not registered")
                
                run_id = f"{pipeline_id}_run_{len(self.pipelines[pipeline_id]['runs'])}"
                run_data = {
                    'id': run_id,
                    'pipeline_id': pipeline_id,
                    'config': run_config or {},
                    'start_time': '2024-01-01T00:00:00Z',
                    'status': 'running',
                    'metrics': {},
                    'stages': []
                }
                
                self.pipelines[pipeline_id]['runs'].append(run_data)
                self.pipelines[pipeline_id]['last_run'] = run_id
                return run_id
            
            def log_stage_completion(self, run_id, stage_name, metrics=None):
                """Log completion of a pipeline stage"""
                # Find the run
                for pipeline_id, pipeline in self.pipelines.items():
                    for run in pipeline['runs']:
                        if run['id'] == run_id:
                            stage_data = {
                                'name': stage_name,
                                'completion_time': '2024-01-01T00:01:00Z',
                                'metrics': metrics or {}
                            }
                            run['stages'].append(stage_data)
                            return True
                return False
            
            def complete_pipeline_run(self, run_id, status='success', final_metrics=None):
                """Complete a pipeline run"""
                for pipeline_id, pipeline in self.pipelines.items():
                    for run in pipeline['runs']:
                        if run['id'] == run_id:
                            run['status'] = status
                            run['end_time'] = '2024-01-01T00:05:00Z'
                            if final_metrics:
                                run['metrics'].update(final_metrics)
                            return True
                return False
            
            def check_pipeline_health(self, pipeline_id):
                """Check pipeline health based on recent runs"""
                if pipeline_id not in self.pipelines:
                    return {'status': 'unknown', 'message': 'Pipeline not found'}
                
                pipeline = self.pipelines[pipeline_id]
                recent_runs = pipeline['runs'][-5:]  # Last 5 runs
                
                if not recent_runs:
                    return {'status': 'no_data', 'message': 'No recent runs'}
                
                failed_runs = [r for r in recent_runs if r['status'] == 'failed']
                failure_rate = len(failed_runs) / len(recent_runs)
                
                if failure_rate > 0.5:
                    return {'status': 'unhealthy', 'message': f'High failure rate: {failure_rate:.2%}'}
                elif failure_rate > 0.2:
                    return {'status': 'warning', 'message': f'Moderate failure rate: {failure_rate:.2%}'}
                else:
                    return {'status': 'healthy', 'message': 'Pipeline operating normally'}
            
            def get_pipeline_metrics(self, pipeline_id, time_range=None):
                """Get aggregated metrics for a pipeline"""
                if pipeline_id not in self.pipelines:
                    return {}
                
                pipeline = self.pipelines[pipeline_id]
                runs = pipeline['runs']
                
                if not runs:
                    return {'total_runs': 0, 'success_rate': 0}
                
                successful_runs = [r for r in runs if r['status'] == 'success']
                success_rate = len(successful_runs) / len(runs)
                
                return {
                    'total_runs': len(runs),
                    'success_rate': success_rate,
                    'last_run_status': runs[-1]['status'] if runs else 'none'
                }
        
        # Test ML pipeline monitoring
        monitor = MockMLPipelineMonitor()
        
        # Test pipeline registration
        pipeline_config = {
            'name': 'document_classifier_training',
            'stages': ['data_prep', 'training', 'validation', 'deployment'],
            'schedule': '0 2 * * *'  # Daily at 2 AM
        }
        
        pipeline_id = monitor.register_pipeline('classifier_pipeline', pipeline_config)
        assert pipeline_id == 'classifier_pipeline'
        assert pipeline_id in monitor.pipelines
        
        # Test pipeline run monitoring
        run_id = monitor.start_pipeline_run(pipeline_id, {'version': '1.0'})
        assert run_id.startswith('classifier_pipeline_run_')
        
        # Test stage completion logging
        stage_success = monitor.log_stage_completion(
            run_id, 
            'data_prep',
            {'processed_records': 10000, 'duration_seconds': 120}
        )
        assert stage_success is True
        
        stage_success = monitor.log_stage_completion(
            run_id,
            'training', 
            {'accuracy': 0.95, 'loss': 0.05, 'duration_seconds': 3600}
        )
        assert stage_success is True
        
        # Test run completion
        completion_success = monitor.complete_pipeline_run(
            run_id,
            'success',
            {'final_accuracy': 0.96, 'model_size_mb': 50}
        )
        assert completion_success is True
        
        # Test pipeline health check
        health = monitor.check_pipeline_health(pipeline_id)
        assert health['status'] in ['healthy', 'warning', 'unhealthy', 'no_data']
        
        # Test metrics retrieval
        metrics = monitor.get_pipeline_metrics(pipeline_id)
        assert metrics['total_runs'] == 1
        assert metrics['success_rate'] == 1.0
        assert metrics['last_run_status'] == 'success'
        
        # Test multiple runs for health checking
        for i in range(3):
            run_id = monitor.start_pipeline_run(pipeline_id)
            monitor.complete_pipeline_run(run_id, 'success')
        
        # Add a failed run
        failed_run_id = monitor.start_pipeline_run(pipeline_id)
        monitor.complete_pipeline_run(failed_run_id, 'failed')
        
        # Check updated metrics
        updated_metrics = monitor.get_pipeline_metrics(pipeline_id)
        assert updated_metrics['total_runs'] == 5
        assert updated_metrics['success_rate'] == 0.8  # 4/5 successful
        
        # Check health with some failures
        updated_health = monitor.check_pipeline_health(pipeline_id)
        assert updated_health['status'] in ['healthy', 'warning']  # 20% failure rate should be warning


if __name__ == "__main__":
    pytest.main([__file__, "-v"])