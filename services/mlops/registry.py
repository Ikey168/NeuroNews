"""
MLflow Model Registry Helper for NeuroNews.

This module provides a standardized way to manage model lifecycle using MLflow Model Registry,
including model registration, versioning, stage transitions, and deployment management.

Implements Issue #221: MLflow Model Registry for model versioning and deployment
"""

import os
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import mlflow
import mlflow.tracking
from mlflow.tracking import MlflowClient
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException
import warnings
from datetime import datetime, timedelta


class ModelStage(Enum):
    """Standard model stages in MLflow Model Registry."""
    NONE = "None"
    STAGING = "Staging" 
    PRODUCTION = "Production"
    ARCHIVED = "Archived"


class TransitionRequirement(Enum):
    """Requirements for stage transitions."""
    MANUAL_APPROVAL = "manual"
    AUTOMATIC = "automatic"
    PERFORMANCE_GATE = "performance"


@dataclass
class ModelMetadata:
    """Metadata for registered models."""
    name: str
    description: str
    tags: Dict[str, str]
    owner: str
    use_case: str
    performance_metrics: Dict[str, float]
    deployment_target: str


@dataclass 
class ModelPerformanceGate:
    """Performance requirements for stage transitions."""
    metric_name: str
    threshold: float
    comparison: str  # "greater", "less", "equal"
    
    def check(self, value: float) -> bool:
        """Check if value meets performance gate."""
        if self.comparison == "greater":
            return value > self.threshold
        elif self.comparison == "less":
            return value < self.threshold
        elif self.comparison == "equal":
            return abs(value - self.threshold) < 0.001
        else:
            raise ValueError(f"Invalid comparison: {self.comparison}")


class NeuroNewsModelRegistry:
    """
    MLflow Model Registry wrapper for NeuroNews model lifecycle management.
    
    Provides standardized model registration, versioning, stage transitions,
    and deployment management with NeuroNews-specific conventions.
    """
    
    # Standard model names for NeuroNews
    STANDARD_MODELS = {
        "neuro_sentiment_classifier": "News article sentiment classification model",
        "neuro_embeddings_encoder": "News article text embedding generation model", 
        "neuro_rag_retriever": "RAG retrieval and ranking model",
        "neuro_topic_extractor": "News topic and keyword extraction model",
        "neuro_summarizer": "News article summarization model",
        "neuro_clustering_engine": "News article clustering and categorization model"
    }
    
    # Performance gates for different model types
    DEFAULT_PERFORMANCE_GATES = {
        "neuro_sentiment_classifier": [
            ModelPerformanceGate("accuracy", 0.85, "greater"),
            ModelPerformanceGate("f1_score", 0.80, "greater")
        ],
        "neuro_embeddings_encoder": [
            ModelPerformanceGate("similarity_score", 0.75, "greater"),
            ModelPerformanceGate("retrieval_recall_at_10", 0.70, "greater")
        ],
        "neuro_rag_retriever": [
            ModelPerformanceGate("relevance_score", 0.80, "greater"),
            ModelPerformanceGate("answer_quality", 0.75, "greater")
        ]
    }
    
    def __init__(self, tracking_uri: Optional[str] = None):
        """
        Initialize MLflow Model Registry client.
        
        Args:
            tracking_uri: MLflow tracking server URI. If None, uses environment variable.
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        elif os.environ.get("MLFLOW_TRACKING_URI"):
            mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        else:
            # Default to local file store
            mlflow.set_tracking_uri("file:./mlruns")
            
        self.client = MlflowClient()
        
    def register_model(
        self,
        model_uri: str,
        name: str,
        metadata: Optional[ModelMetadata] = None,
        wait_for_completion: bool = True
    ) -> ModelVersion:
        """
        Register a model with the MLflow Model Registry.
        
        Args:
            model_uri: URI of the model artifact (e.g., runs:/<run_id>/model)
            name: Name for the registered model (should use standard names)
            metadata: Additional metadata for the model
            wait_for_completion: Whether to wait for model registration to complete
            
        Returns:
            ModelVersion object for the registered model version
            
        Raises:
            ValueError: If model name is not in standard names and no description provided
        """
        # Validate model name
        if name not in self.STANDARD_MODELS and (not metadata or not metadata.description):
            warnings.warn(
                f"Model '{name}' is not in standard models: {list(self.STANDARD_MODELS.keys())}. "
                f"Consider using a standard model name or providing detailed metadata."
            )
        
        try:
            # Create registered model if it doesn't exist
            try:
                registered_model = self.client.get_registered_model(name)
                print(f"Using existing registered model: {name}")
            except MlflowException:
                # Model doesn't exist, create it
                description = (metadata.description if metadata 
                             else self.STANDARD_MODELS.get(name, f"NeuroNews {name} model"))
                
                tags = {}
                if metadata:
                    tags.update(metadata.tags)
                    tags.update({
                        "owner": metadata.owner,
                        "use_case": metadata.use_case,
                        "deployment_target": metadata.deployment_target
                    })
                
                # Add standard NeuroNews tags
                tags.update({
                    "project": "neuronews",
                    "created_date": datetime.now().isoformat(),
                    "registry_version": "1.0.0"
                })
                
                registered_model = self.client.create_registered_model(
                    name=name,
                    description=description,
                    tags=tags
                )
                print(f"Created new registered model: {name}")
            
            # Register model version
            model_version = self.client.create_model_version(
                name=name,
                source=model_uri,
                description=f"Model version created on {datetime.now().isoformat()}"
            )
            
            # Add version-specific tags if metadata provided
            if metadata:
                version_tags = {
                    "performance_metrics": str(metadata.performance_metrics),
                    "registration_date": datetime.now().isoformat()
                }
                
                for key, value in version_tags.items():
                    self.client.set_model_version_tag(
                        name=name,
                        version=model_version.version,
                        key=key,
                        value=str(value)
                    )
            
            # Wait for model version to be ready
            if wait_for_completion:
                self._wait_for_model_version_ready(name, model_version.version)
            
            print(f"Successfully registered {name} version {model_version.version}")
            return model_version
            
        except Exception as e:
            print(f"Failed to register model {name}: {e}")
            raise
    
    def transition_model_stage(
        self,
        name: str,
        version: Union[str, int],
        stage: ModelStage,
        description: Optional[str] = None,
        check_performance_gates: bool = True
    ) -> ModelVersion:
        """
        Transition a model version to a new stage.
        
        Args:
            name: Registered model name
            version: Model version number
            stage: Target stage
            description: Description for the transition
            check_performance_gates: Whether to check performance gates before transition
            
        Returns:
            Updated ModelVersion object
            
        Raises:
            ValueError: If performance gates are not met
        """
        version_str = str(version)
        
        # Check performance gates if transitioning to Production
        if stage == ModelStage.PRODUCTION and check_performance_gates:
            if not self._check_performance_gates(name, version_str):
                raise ValueError(
                    f"Model {name} version {version} does not meet performance gates for Production stage"
                )
        
        # Perform transition
        try:
            updated_version = self.client.transition_model_version_stage(
                name=name,
                version=version_str,
                stage=stage.value
            )
            
            # Add description as a tag if provided
            if description:
                self.client.set_model_version_tag(
                    name=name,
                    version=version_str,
                    key="transition_description",
                    value=description
                )
            
            print(f"Successfully transitioned {name} v{version} to {stage.value}")
            return updated_version
            
        except Exception as e:
            print(f"Failed to transition {name} v{version} to {stage.value}: {e}")
            raise
    
    def get_model_versions(
        self,
        name: str,
        stages: Optional[List[ModelStage]] = None
    ) -> List[ModelVersion]:
        """
        Get model versions for a registered model.
        
        Args:
            name: Registered model name
            stages: Filter by stages (if None, returns all versions)
            
        Returns:
            List of ModelVersion objects
        """
        try:
            all_versions = self.client.get_registered_model(name).latest_versions
            
            if not stages:
                return all_versions
            
            stage_values = [stage.value for stage in stages]
            return [v for v in all_versions if v.current_stage in stage_values]
            
        except Exception as e:
            print(f"Failed to get model versions for {name}: {e}")
            return []
    
    def get_production_model(self, name: str) -> Optional[ModelVersion]:
        """
        Get the current production version of a model.
        
        Args:
            name: Registered model name
            
        Returns:
            ModelVersion in Production stage, or None if not found
        """
        production_versions = self.get_model_versions(name, [ModelStage.PRODUCTION])
        return production_versions[0] if production_versions else None
    
    def get_latest_model(self, name: str) -> Optional[ModelVersion]:
        """
        Get the latest version of a model regardless of stage.
        
        Args:
            name: Registered model name
            
        Returns:
            Latest ModelVersion, or None if not found
        """
        try:
            registered_model = self.client.get_registered_model(name)
            if registered_model.latest_versions:
                # Sort by version number and return latest
                latest = max(registered_model.latest_versions, 
                           key=lambda v: int(v.version))
                return latest
            return None
        except Exception as e:
            print(f"Failed to get latest model for {name}: {e}")
            return None
    
    def compare_model_versions(
        self,
        name: str,
        version1: Union[str, int],
        version2: Union[str, int]
    ) -> Dict[str, Any]:
        """
        Compare two model versions.
        
        Args:
            name: Registered model name
            version1: First model version
            version2: Second model version
            
        Returns:
            Dictionary with comparison results
        """
        try:
            v1 = self.client.get_model_version(name, str(version1))
            v2 = self.client.get_model_version(name, str(version2))
            
            # Extract performance metrics from tags
            v1_metrics = self._extract_performance_metrics(v1)
            v2_metrics = self._extract_performance_metrics(v2)
            
            comparison = {
                "model_name": name,
                "version1": {
                    "version": v1.version,
                    "stage": v1.current_stage,
                    "creation_date": v1.creation_timestamp,
                    "metrics": v1_metrics
                },
                "version2": {
                    "version": v2.version,
                    "stage": v2.current_stage,
                    "creation_date": v2.creation_timestamp,
                    "metrics": v2_metrics
                },
                "improvements": {}
            }
            
            # Calculate improvements
            for metric in set(v1_metrics.keys()) & set(v2_metrics.keys()):
                diff = v2_metrics[metric] - v1_metrics[metric]
                comparison["improvements"][metric] = {
                    "absolute_change": diff,
                    "relative_change": (diff / v1_metrics[metric]) * 100 if v1_metrics[metric] != 0 else 0
                }
            
            return comparison
            
        except Exception as e:
            print(f"Failed to compare model versions: {e}")
            return {}
    
    def archive_old_versions(
        self,
        name: str,
        keep_latest_n: int = 3,
        exclude_production: bool = True
    ) -> List[str]:
        """
        Archive old model versions to clean up the registry.
        
        Args:
            name: Registered model name
            keep_latest_n: Number of latest versions to keep
            exclude_production: Whether to exclude Production models from archiving
            
        Returns:
            List of archived version numbers
        """
        try:
            registered_model = self.client.get_registered_model(name)
            all_versions = registered_model.latest_versions
            
            # Sort versions by creation timestamp (newest first)
            sorted_versions = sorted(
                all_versions,
                key=lambda v: v.creation_timestamp,
                reverse=True
            )
            
            archived_versions = []
            
            for i, version in enumerate(sorted_versions):
                # Skip if it's one of the latest N versions
                if i < keep_latest_n:
                    continue
                
                # Skip if it's in Production and we're excluding those
                if exclude_production and version.current_stage == ModelStage.PRODUCTION.value:
                    continue
                
                # Archive the version
                try:
                    self.client.transition_model_version_stage(
                        name=name,
                        version=version.version,
                        stage=ModelStage.ARCHIVED.value
                    )
                    
                    # Add archival description as tag
                    self.client.set_model_version_tag(
                        name=name,
                        version=version.version,
                        key="archival_description",
                        value=f"Automated archival on {datetime.now().isoformat()}"
                    )
                    
                    archived_versions.append(version.version)
                    print(f"Archived {name} version {version.version}")
                except Exception as e:
                    print(f"Failed to archive {name} version {version.version}: {e}")
            
            return archived_versions
            
        except Exception as e:
            print(f"Failed to archive old versions for {name}: {e}")
            return []
    
    def get_model_deployment_info(self, name: str) -> Dict[str, Any]:
        """
        Get deployment information for all versions of a model.
        
        Args:
            name: Registered model name
            
        Returns:
            Dictionary with deployment information
        """
        try:
            production_version = self.get_production_model(name)
            staging_versions = self.get_model_versions(name, [ModelStage.STAGING])
            latest_version = self.get_latest_model(name)
            
            deployment_info = {
                "model_name": name,
                "production": {
                    "version": production_version.version if production_version else None,
                    "creation_date": production_version.creation_timestamp if production_version else None,
                    "model_uri": f"models:/{name}/Production" if production_version else None
                },
                "staging": [
                    {
                        "version": v.version,
                        "creation_date": v.creation_timestamp,
                        "model_uri": f"models:/{name}/{v.version}"
                    }
                    for v in staging_versions
                ],
                "latest": {
                    "version": latest_version.version if latest_version else None,
                    "stage": latest_version.current_stage if latest_version else None,
                    "model_uri": f"models:/{name}/latest" if latest_version else None
                }
            }
            
            return deployment_info
            
        except Exception as e:
            print(f"Failed to get deployment info for {name}: {e}")
            return {}
    
    def _check_performance_gates(self, name: str, version: str) -> bool:
        """Check if model version meets performance gates."""
        gates = self.DEFAULT_PERFORMANCE_GATES.get(name, [])
        
        if not gates:
            print(f"No performance gates defined for {name}, allowing transition")
            return True
        
        try:
            model_version = self.client.get_model_version(name, version)
            metrics = self._extract_performance_metrics(model_version)
            
            for gate in gates:
                if gate.metric_name not in metrics:
                    print(f"Performance gate metric {gate.metric_name} not found in model metrics")
                    return False
                
                if not gate.check(metrics[gate.metric_name]):
                    print(f"Performance gate failed: {gate.metric_name} = {metrics[gate.metric_name]}, "
                          f"required {gate.comparison} {gate.threshold}")
                    return False
            
            print(f"All performance gates passed for {name} v{version}")
            return True
            
        except Exception as e:
            print(f"Error checking performance gates: {e}")
            return False
    
    def _extract_performance_metrics(self, model_version: ModelVersion) -> Dict[str, float]:
        """Extract performance metrics from model version tags and source run."""
        metrics = {}
        
        try:
            # Try to get metrics from source run
            if model_version.run_id:
                run = self.client.get_run(model_version.run_id)
                metrics.update({k: float(v) for k, v in run.data.metrics.items()})
            
            # Also check model version tags for performance_metrics
            for tag_key, tag_value in (model_version.tags or {}).items():
                if tag_key == "performance_metrics":
                    try:
                        # Parse string representation of metrics dict
                        import ast
                        parsed_metrics = ast.literal_eval(tag_value)
                        if isinstance(parsed_metrics, dict):
                            metrics.update({k: float(v) for k, v in parsed_metrics.items()})
                    except (ValueError, SyntaxError):
                        pass
        except Exception as e:
            print(f"Warning: Could not extract performance metrics: {e}")
        
        return metrics
    
    def _wait_for_model_version_ready(self, name: str, version: str, timeout_seconds: int = 60):
        """Wait for model version to be ready."""
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            try:
                model_version = self.client.get_model_version(name, version)
                if model_version.status == "READY":
                    return
                elif model_version.status == "FAILED_REGISTRATION":
                    raise MlflowException(f"Model version {name}:{version} failed registration")
                
                time.sleep(2)
            except Exception as e:
                print(f"Error waiting for model version {name}:{version}: {e}")
                break
        
        print(f"Warning: Model version {name}:{version} may not be ready yet")


def setup_model_registry(tracking_uri: str = "http://localhost:5001") -> NeuroNewsModelRegistry:
    """
    Setup and return NeuroNews Model Registry instance.
    
    Args:
        tracking_uri: MLflow tracking server URI
        
    Returns:
        Configured NeuroNewsModelRegistry instance
    """
    return NeuroNewsModelRegistry(tracking_uri)


def register_model_from_run(
    run_id: str,
    model_name: str,
    model_path: str = "model",
    metadata: Optional[ModelMetadata] = None
) -> ModelVersion:
    """
    Helper function to register a model from an MLflow run.
    
    Args:
        run_id: MLflow run ID containing the model
        model_name: Name for the registered model
        model_path: Path to model artifact within the run (default: "model")
        metadata: Optional model metadata
        
    Returns:
        ModelVersion object for the registered model
    """
    registry = NeuroNewsModelRegistry()
    model_uri = f"runs:/{run_id}/{model_path}"
    
    return registry.register_model(
        model_uri=model_uri,
        name=model_name,
        metadata=metadata
    )


def promote_to_production(
    model_name: str,
    version: Union[str, int],
    check_performance: bool = True
) -> ModelVersion:
    """
    Helper function to promote a model version to production.
    
    Args:
        model_name: Registered model name
        version: Model version to promote
        check_performance: Whether to check performance gates
        
    Returns:
        Updated ModelVersion object
    """
    registry = NeuroNewsModelRegistry()
    
    return registry.transition_model_stage(
        name=model_name,
        version=version,
        stage=ModelStage.PRODUCTION,
        description=f"Promoted to production based on validation results",
        check_performance_gates=check_performance
    )


def get_production_model_uri(model_name: str) -> Optional[str]:
    """
    Get the MLflow URI for the production version of a model.
    
    Args:
        model_name: Registered model name
        
    Returns:
        MLflow model URI for production version, or None if not found
    """
    registry = NeuroNewsModelRegistry()
    production_version = registry.get_production_model(model_name)
    
    if production_version:
        return f"models:/{model_name}/Production"
    else:
        return None


def list_all_models() -> Dict[str, Any]:
    """
    List all registered models with their current versions and stages.
    
    Returns:
        Dictionary with model information
    """
    registry = NeuroNewsModelRegistry()
    
    try:
        registered_models = registry.client.list_registered_models()
        
        models_info = {}
        for model in registered_models:
            models_info[model.name] = {
                "description": model.description,
                "creation_timestamp": model.creation_timestamp,
                "last_updated_timestamp": model.last_updated_timestamp,
                "latest_versions": [
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "creation_timestamp": v.creation_timestamp
                    }
                    for v in model.latest_versions
                ],
                "tags": model.tags
            }
        
        return models_info
        
    except Exception as e:
        print(f"Failed to list models: {e}")
        return {}
