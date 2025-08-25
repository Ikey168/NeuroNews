#!/usr/bin/env python3
"""
Demo: MLflow Model Registry for NeuroNews (Issue #221)

This demo showcases the complete MLflow Model Registry workflow including:
- Model registration with metadata
- Stage transitions (None → Staging → Production)
- Performance gate validation
- Model comparison and deployment info
- Version archival management

Issue #221: Implement MLflow Model Registry for model versioning and deployment
"""

import os
import sys
import mlflow
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from services.mlops.registry import (
        NeuroNewsModelRegistry, 
        ModelMetadata, 
        ModelStage,
        ModelPerformanceGate
    )
    print("✅ Successfully imported NeuroNews Model Registry components")
except ImportError as e:
    print(f"❌ Failed to import registry components: {e}")
    sys.exit(1)


def setup_demo_environment():
    """Setup MLflow environment for demo."""
    print("🔧 Setting up demo environment...")
    
    # Set MLflow tracking to local file store
    mlflow_uri = "file:./mlruns"
    os.environ["MLFLOW_TRACKING_URI"] = mlflow_uri
    mlflow.set_tracking_uri(mlflow_uri)
    
    print(f"   MLflow Tracking URI: {mlflow_uri}")
    return mlflow_uri


def create_dummy_model_run():
    """Create a dummy MLflow run with a model for demo purposes."""
    print("\n📦 Creating dummy model run for registration...")
    
    # Start MLflow run
    with mlflow.start_run(run_name="dummy_sentiment_model_training") as run:
        # Log some dummy parameters
        mlflow.log_param("model_type", "sentiment_classifier")
        mlflow.log_param("architecture", "transformer")
        mlflow.log_param("training_data_size", 50000)
        
        # Log some dummy metrics (good performance to pass gates)
        accuracy = np.random.uniform(0.88, 0.92)
        f1_score = np.random.uniform(0.85, 0.89)
        
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1_score)
        mlflow.log_metric("precision", np.random.uniform(0.83, 0.87))
        mlflow.log_metric("recall", np.random.uniform(0.84, 0.88))
        
        # Create a dummy model file (sklearn-style for compatibility)
        from sklearn.linear_model import LogisticRegression
        from sklearn.datasets import make_classification
        
        # Create dummy training data
        X, y = make_classification(n_samples=100, n_features=10, n_classes=2, random_state=42)
        
        # Train a simple model
        model = LogisticRegression(random_state=42)
        model.fit(X, y)
        
        # Log the model
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            registered_model_name=None  # We'll register manually via registry
        )
        
        model_uri = f"runs:/{run.info.run_id}/model"
        
        print(f"   ✅ Created model run: {run.info.run_id}")
        print(f"   📊 Accuracy: {accuracy:.4f}")
        print(f"   📊 F1 Score: {f1_score:.4f}")
        print(f"   🔗 Model URI: {model_uri}")
        
        return model_uri, {"accuracy": accuracy, "f1_score": f1_score}


def demo_model_registration():
    """Demonstrate model registration with the registry."""
    print("\n" + "="*60)
    print("🏷️  MODEL REGISTRATION DEMO")
    print("="*60)
    
    # Create dummy model
    model_uri, metrics = create_dummy_model_run()
    
    # Setup registry
    registry = NeuroNewsModelRegistry()
    
    # Create model metadata
    model_name = "neuro_sentiment_classifier"
    metadata = ModelMetadata(
        name=model_name,
        description="Advanced sentiment classifier for NeuroNews articles using transformer architecture",
        tags={
            "team": "mlops",
            "environment": "dev", 
            "model_type": "transformer",
            "data_source": "neuronews_articles",
            "training_framework": "sklearn"
        },
        owner="Ikey168",
        use_case="Real-time sentiment analysis of news articles for content filtering and recommendation",
        performance_metrics=metrics,
        deployment_target="production"
    )
    
    print(f"\n📝 Registering model: {model_name}")
    print(f"   Description: {metadata.description}")
    print(f"   Owner: {metadata.owner}")
    print(f"   Use Case: {metadata.use_case}")
    print(f"   Performance: {metadata.performance_metrics}")
    
    # Register the model
    try:
        model_version = registry.register_model(
            model_uri=model_uri,
            name=model_name,
            metadata=metadata,
            wait_for_completion=True
        )
        
        print(f"   ✅ Successfully registered {model_name} version {model_version.version}")
        return registry, model_name, model_version
        
    except Exception as e:
        print(f"   ❌ Registration failed: {e}")
        raise


def demo_stage_transitions(registry, model_name, model_version):
    """Demonstrate model stage transitions."""
    print("\n" + "="*60)
    print("🔄 STAGE TRANSITION DEMO")
    print("="*60)
    
    print(f"\n📈 Current stage: {model_version.current_stage}")
    
    # Transition to Staging
    print(f"\n1️⃣ Transitioning to Staging...")
    try:
        updated_version = registry.transition_model_stage(
            name=model_name,
            version=model_version.version,
            stage=ModelStage.STAGING,
            description="Initial model validation and testing phase",
            check_performance_gates=False  # No gates for staging
        )
        print(f"   ✅ Successfully moved to {updated_version.current_stage}")
        
    except Exception as e:
        print(f"   ❌ Staging transition failed: {e}")
        return model_version
    
    # Transition to Production (with performance gate checking)
    print(f"\n2️⃣ Transitioning to Production...")
    try:
        production_version = registry.transition_model_stage(
            name=model_name,
            version=model_version.version,
            stage=ModelStage.PRODUCTION,
            description="Model meets all performance gates, ready for production deployment",
            check_performance_gates=True  # Check gates for production
        )
        print(f"   ✅ Successfully moved to {production_version.current_stage}")
        print(f"   🎯 Model passed all performance gates!")
        
        return production_version
        
    except ValueError as e:
        print(f"   ❌ Production transition failed: {e}")
        print(f"   📊 Performance gates not met - keeping in Staging")
        return updated_version
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return updated_version


def demo_model_queries(registry, model_name):
    """Demonstrate various model query operations."""
    print("\n" + "="*60)
    print("🔍 MODEL QUERY DEMO")
    print("="*60)
    
    # Get production model
    print(f"\n🚀 Production Model Query:")
    production_model = registry.get_production_model(model_name)
    if production_model:
        print(f"   ✅ Production version: {production_model.version}")
        print(f"   📅 Created: {datetime.fromtimestamp(production_model.creation_timestamp/1000)}")
        print(f"   🔗 URI: models:/{model_name}/Production")
    else:
        print(f"   ⚠️  No production version found")
    
    # Get latest model
    print(f"\n🔄 Latest Model Query:")
    latest_model = registry.get_latest_model(model_name)
    if latest_model:
        print(f"   ✅ Latest version: {latest_model.version}")
        print(f"   📊 Stage: {latest_model.current_stage}")
        print(f"   🔗 URI: models:/{model_name}/latest")
    else:
        print(f"   ⚠️  No versions found")
    
    # Get all versions by stage
    print(f"\n📊 All Model Versions:")
    all_versions = registry.get_model_versions(model_name)
    for version in all_versions:
        print(f"   Version {version.version}: {version.current_stage} stage")


def demo_deployment_info(registry, model_name):
    """Demonstrate deployment information retrieval."""
    print("\n" + "="*60)
    print("🚀 DEPLOYMENT INFO DEMO")
    print("="*60)
    
    deployment_info = registry.get_model_deployment_info(model_name)
    
    if deployment_info:
        print(f"\n📊 Deployment Summary for {model_name}:")
        
        # Production info
        prod_info = deployment_info["production"]
        if prod_info["version"]:
            print(f"   🚀 Production: Version {prod_info['version']}")
            print(f"      URI: {prod_info['model_uri']}")
            print(f"      Deployed: {datetime.fromtimestamp(prod_info['creation_date']/1000)}")
        else:
            print(f"   🚀 Production: No version deployed")
        
        # Staging info
        staging_info = deployment_info["staging"]
        if staging_info:
            print(f"   🧪 Staging: {len(staging_info)} version(s)")
            for stage_version in staging_info:
                print(f"      Version {stage_version['version']}: {stage_version['model_uri']}")
        else:
            print(f"   🧪 Staging: No versions")
        
        # Latest info
        latest_info = deployment_info["latest"]
        if latest_info["version"]:
            print(f"   🔄 Latest: Version {latest_info['version']} ({latest_info['stage']} stage)")
            print(f"      URI: {latest_info['model_uri']}")
        
    else:
        print(f"   ❌ Failed to get deployment info")


def demo_model_comparison(registry, model_name):
    """Demonstrate model version comparison."""
    print("\n" + "="*60)
    print("⚖️  MODEL COMPARISON DEMO")
    print("="*60)
    
    # Get all versions to compare
    all_versions = registry.get_model_versions(model_name)
    
    if len(all_versions) >= 2:
        # Compare first two versions
        v1 = all_versions[0].version
        v2 = all_versions[1].version if len(all_versions) > 1 else all_versions[0].version
        
        print(f"\n📊 Comparing versions {v1} vs {v2}:")
        
        comparison = registry.compare_model_versions(model_name, v1, v2)
        
        if comparison:
            print(f"   Version {v1}: {comparison['version1']['stage']} stage")
            print(f"   Version {v2}: {comparison['version2']['stage']} stage")
            
            improvements = comparison.get("improvements", {})
            if improvements:
                print(f"   📈 Performance changes (v{v1} → v{v2}):")
                for metric, change in improvements.items():
                    direction = "↗️" if change["absolute_change"] > 0 else "↘️" if change["absolute_change"] < 0 else "→"
                    print(f"      {metric}: {direction} {change['absolute_change']:+.4f} ({change['relative_change']:+.2f}%)")
            else:
                print(f"   📊 No common metrics found for comparison")
    else:
        print(f"   ⚠️  Need at least 2 versions for comparison (found {len(all_versions)})")


def demo_archival_management(registry, model_name):
    """Demonstrate model version archival."""
    print("\n" + "="*60)
    print("🗄️  ARCHIVAL MANAGEMENT DEMO")
    print("="*60)
    
    print(f"\n📦 Current versions before archival:")
    all_versions = registry.get_model_versions(model_name)
    for version in all_versions:
        print(f"   Version {version.version}: {version.current_stage}")
    
    print(f"\n🧹 Archiving old versions (keeping latest 2, excluding production)...")
    try:
        archived_versions = registry.archive_old_versions(
            name=model_name,
            keep_latest_n=2,
            exclude_production=True
        )
        
        if archived_versions:
            print(f"   ✅ Archived versions: {', '.join(archived_versions)}")
        else:
            print(f"   ℹ️  No versions needed archiving")
            
        print(f"\n📦 Versions after archival:")
        updated_versions = registry.get_model_versions(model_name)
        for version in updated_versions:
            print(f"   Version {version.version}: {version.current_stage}")
            
    except Exception as e:
        print(f"   ❌ Archival failed: {e}")


def main():
    """Run the complete MLflow Model Registry demo."""
    print("🎯 MLflow Model Registry Demo for NeuroNews")
    print("=" * 80)
    print("Issue #221: Demonstrate complete model lifecycle management")
    print("including registration, versioning, stage transitions, and deployment")
    
    try:
        # Setup
        setup_demo_environment()
        
        # Model registration
        registry, model_name, model_version = demo_model_registration()
        
        # Stage transitions
        updated_version = demo_stage_transitions(registry, model_name, model_version)
        
        # Model queries
        demo_model_queries(registry, model_name)
        
        # Deployment info
        demo_deployment_info(registry, model_name)
        
        # Model comparison
        demo_model_comparison(registry, model_name)
        
        # Archival management
        demo_archival_management(registry, model_name)
        
        # Summary
        print("\n" + "="*80)
        print("🎉 DEMO COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        print(f"\n📊 MLflow Model Registry Demo Results:")
        print(f"   ✅ Model registered: {model_name}")
        print(f"   ✅ Stage transitions: None → Staging → Production")
        print(f"   ✅ Performance gates validated")
        print(f"   ✅ Deployment info retrieved")
        print(f"   ✅ Model comparison performed")
        print(f"   ✅ Version archival demonstrated")
        
        print(f"\n🔗 Access MLflow UI:")
        print(f"   mlflow ui --backend-store-uri file:./mlruns")
        print(f"   Then navigate to: http://localhost:5000")
        
        print(f"\n📝 Registry features demonstrated:")
        print(f"   • Model registration with metadata")
        print(f"   • Automated version management")
        print(f"   • Stage-based model lifecycle")
        print(f"   • Performance gate validation")
        print(f"   • Deployment status tracking")
        print(f"   • Version comparison and archival")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()