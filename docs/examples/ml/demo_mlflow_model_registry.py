#!/usr/bin/env python3
"""
Demonstration of MLflow Model Registry Implementation
Issue #221: Show comprehensive model lifecycle management

This script demonstrates the MLflow Model Registry implementation,
including model registration, versioning, stage transitions, and deployment.
"""

import os
import sys
import numpy as np
import mlflow
import mlflow.sklearn
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
from typing import Dict, Any
import time

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mlops.tracking import mlrun
from services.mlops.registry import (
    NeuroNewsModelRegistry,
    ModelMetadata,
    ModelStage,
    register_model_from_run,
    promote_to_production,
    get_production_model_uri,
    list_all_models,
    setup_model_registry
)


def setup_demo_environment():
    """Setup environment for the demo."""
    print("🔧 Setting up demo environment...")
    
    # Set required environment variables
    os.environ["NEURONEWS_ENV"] = "dev"
    os.environ["NEURONEWS_PIPELINE"] = "model_registry_demo"
    os.environ["NEURONEWS_DATA_VERSION"] = "v1.0.0"
    
    # Set MLflow tracking to local file store
    os.environ["MLFLOW_TRACKING_URI"] = "file:./mlruns"
    
    print("✅ Environment configured:")
    print(f"   MLFLOW_TRACKING_URI: {os.environ['MLFLOW_TRACKING_URI']}")
    print(f"   NEURONEWS_ENV: {os.environ['NEURONEWS_ENV']}")


def train_sentiment_model() -> str:
    """Train a sentiment classification model and return run ID."""
    print("\n" + "="*60)
    print("🤖 TRAINING SENTIMENT CLASSIFICATION MODEL")
    print("="*60)
    
    # Generate synthetic sentiment data
    X, y = make_classification(
        n_samples=1000,
        n_features=20,
        n_informative=15,
        n_redundant=5,
        n_classes=3,  # positive, negative, neutral
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Train model with MLflow tracking
    with mlrun(
        name="sentiment_classifier_training",
        experiment="neuro_news_indexing",
        tags={
            "data_version": "v1.0.0",
            "notes": "Baseline sentiment classifier for model registry demo",
            "model_type": "random_forest",
            "task_type": "classification"
        }
    ) as run:
        # Train Random Forest classifier
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42
        )
        model.fit(X_train, y_train)
        
        # Make predictions
        y_pred = model.predict(X_test)
        
        # Calculate metrics
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        # Log parameters
        mlflow.log_param("model_type", "RandomForestClassifier")
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("max_depth", 10)
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("n_samples", X_train.shape[0])
        
        # Log metrics
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)
        mlflow.log_metric("test_samples", len(y_test))
        
        # Log model
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            input_example=X_test[:5],
            signature=mlflow.models.infer_signature(X_train, y_train)
        )
        
        print(f"📈 Model performance:")
        print(f"   Accuracy: {accuracy:.4f}")
        print(f"   F1 Score: {f1:.4f}")
        print(f"🆔 Run ID: {run.info.run_id}")
        
        return run.info.run_id


def train_embeddings_model() -> str:
    """Train an embeddings model and return run ID."""
    print("\n" + "="*60)
    print("🔗 TRAINING EMBEDDINGS MODEL")
    print("="*60)
    
    # Generate synthetic embedding data (regression task)
    X, y = make_regression(
        n_samples=800,
        n_features=30,
        n_informative=25,
        noise=0.1,
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    with mlrun(
        name="embeddings_encoder_training", 
        experiment="neuro_news_indexing",
        tags={
            "data_version": "v1.0.0",
            "notes": "Document embedding encoder for model registry demo",
            "model_type": "linear_regression",
            "task_type": "embedding"
        }
    ) as run:
        # Train Linear Regression model (simulating embedding generation)
        model = LinearRegression()
        model.fit(X_train, y_train)
        
        # Make predictions
        y_pred = model.predict(X_test)
        
        # Calculate metrics
        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        # Simulate embedding-specific metrics
        similarity_score = max(0.5, min(1.0, r2 + 0.2))  # Simulate similarity
        retrieval_recall = max(0.6, min(1.0, r2 + 0.1))  # Simulate retrieval
        
        # Log parameters
        mlflow.log_param("model_type", "LinearRegression")
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("n_samples", X_train.shape[0])
        mlflow.log_param("embedding_dim", 128)
        
        # Log metrics
        mlflow.log_metric("mse", mse)
        mlflow.log_metric("r2_score", r2)
        mlflow.log_metric("similarity_score", similarity_score)
        mlflow.log_metric("retrieval_recall_at_10", retrieval_recall)
        
        # Log model
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            input_example=X_test[:3],
            signature=mlflow.models.infer_signature(X_train, y_train)
        )
        
        print(f"📈 Model performance:")
        print(f"   R² Score: {r2:.4f}")
        print(f"   Similarity Score: {similarity_score:.4f}")
        print(f"   Retrieval Recall@10: {retrieval_recall:.4f}")
        print(f"🆔 Run ID: {run.info.run_id}")
        
        return run.info.run_id


def demonstrate_model_registration():
    """Demonstrate model registration process."""
    print("\n" + "="*60)
    print("📝 MODEL REGISTRATION DEMO")
    print("="*60)
    
    # Train models and get run IDs
    sentiment_run_id = train_sentiment_model()
    embeddings_run_id = train_embeddings_model()
    
    # Initialize model registry
    registry = setup_model_registry()
    
    print(f"\n🗂️  Registering models...")
    
    # Register sentiment model
    sentiment_metadata = ModelMetadata(
        name="neuro_sentiment_classifier",
        description="Random Forest model for news article sentiment classification",
        tags={
            "team": "nlp",
            "domain": "sentiment_analysis",
            "algorithm": "random_forest"
        },
        owner="ml-team",
        use_case="news_sentiment_analysis",
        performance_metrics={"accuracy": 0.87, "f1_score": 0.85},
        deployment_target="production"
    )
    
    sentiment_version = registry.register_model(
        model_uri=f"runs:/{sentiment_run_id}/model",
        name="neuro_sentiment_classifier",
        metadata=sentiment_metadata
    )
    
    print(f"✅ Registered sentiment model: {sentiment_version.name} v{sentiment_version.version}")
    
    # Register embeddings model
    embeddings_metadata = ModelMetadata(
        name="neuro_embeddings_encoder",
        description="Linear model for news article embedding generation",
        tags={
            "team": "search",
            "domain": "embeddings",
            "algorithm": "linear_regression"
        },
        owner="search-team",
        use_case="document_embedding",
        performance_metrics={"similarity_score": 0.82, "retrieval_recall_at_10": 0.78},
        deployment_target="staging"
    )
    
    embeddings_version = registry.register_model(
        model_uri=f"runs:/{embeddings_run_id}/model",
        name="neuro_embeddings_encoder",
        metadata=embeddings_metadata
    )
    
    print(f"✅ Registered embeddings model: {embeddings_version.name} v{embeddings_version.version}")
    
    return {
        "sentiment": {"run_id": sentiment_run_id, "version": sentiment_version},
        "embeddings": {"run_id": embeddings_run_id, "version": embeddings_version}
    }


def demonstrate_stage_transitions(registered_models: Dict[str, Any]):
    """Demonstrate model stage transitions."""
    print("\n" + "="*60)
    print("🔄 STAGE TRANSITIONS DEMO")
    print("="*60)
    
    registry = setup_model_registry()
    
    # Move sentiment model to staging
    print(f"\n1️⃣ Moving sentiment model to Staging...")
    sentiment_version = registered_models["sentiment"]["version"]
    
    staging_version = registry.transition_model_stage(
        name=sentiment_version.name,
        version=sentiment_version.version,
        stage=ModelStage.STAGING,
        description="Moving to staging for validation testing"
    )
    print(f"✅ {staging_version.name} v{staging_version.version} is now in Staging")
    
    # Try to move sentiment model to production (should pass performance gates)
    print(f"\n2️⃣ Attempting to promote sentiment model to Production...")
    try:
        production_version = registry.transition_model_stage(
            name=sentiment_version.name,
            version=sentiment_version.version,
            stage=ModelStage.PRODUCTION,
            description="Promoting to production after successful validation",
            check_performance_gates=True
        )
        print(f"✅ {production_version.name} v{production_version.version} is now in Production")
    except ValueError as e:
        print(f"❌ Failed to promote to production: {e}")
    
    # Move embeddings model to staging  
    print(f"\n3️⃣ Moving embeddings model to Staging...")
    embeddings_version = registered_models["embeddings"]["version"]
    
    staging_embeddings = registry.transition_model_stage(
        name=embeddings_version.name,
        version=embeddings_version.version,
        stage=ModelStage.STAGING,
        description="Initial staging deployment for embeddings model"
    )
    print(f"✅ {staging_embeddings.name} v{staging_embeddings.version} is now in Staging")
    
    # Try to promote embeddings model (might fail performance gates)
    print(f"\n4️⃣ Attempting to promote embeddings model to Production...")
    try:
        production_embeddings = registry.transition_model_stage(
            name=embeddings_version.name,
            version=embeddings_version.version,
            stage=ModelStage.PRODUCTION,
            description="Promoting embeddings model to production",
            check_performance_gates=True
        )
        print(f"✅ {production_embeddings.name} v{production_embeddings.version} is now in Production")
    except ValueError as e:
        print(f"❌ Failed to promote to production: {e}")
        print(f"   This is expected if performance gates are not met")


def demonstrate_model_comparison():
    """Demonstrate model version comparison."""
    print("\n" + "="*60)
    print("📊 MODEL COMPARISON DEMO")
    print("="*60)
    
    registry = setup_model_registry()
    
    # Train a second version of sentiment model with different parameters
    print(f"\n📈 Training improved sentiment model...")
    
    X, y = make_classification(
        n_samples=1200,  # More data
        n_features=25,   # More features
        n_informative=20,
        n_redundant=5,
        n_classes=3,
        random_state=123  # Different seed
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=123
    )
    
    with mlrun(
        name="sentiment_classifier_v2_training",
        experiment="neuro_news_indexing", 
        tags={
            "data_version": "v1.1.0",
            "notes": "Improved sentiment classifier with more data and features",
            "model_type": "logistic_regression",
            "task_type": "classification"
        }
    ) as run:
        # Train Logistic Regression (different algorithm)
        model = LogisticRegression(
            max_iter=1000,
            random_state=123
        )
        model.fit(X_train, y_train)
        
        # Make predictions
        y_pred = model.predict(X_test)
        
        # Calculate metrics (should be better)
        accuracy = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        # Log parameters and metrics
        mlflow.log_param("model_type", "LogisticRegression")
        mlflow.log_param("max_iter", 1000)
        mlflow.log_param("n_features", X_train.shape[1])
        mlflow.log_param("n_samples", X_train.shape[0])
        
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("f1_score", f1)
        
        # Log model
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            input_example=X_test[:5],
            signature=mlflow.models.infer_signature(X_train, y_train)
        )
        
        print(f"📈 Improved model performance:")
        print(f"   Accuracy: {accuracy:.4f}")
        print(f"   F1 Score: {f1:.4f}")
        
        # Register the improved model
        improved_metadata = ModelMetadata(
            name="neuro_sentiment_classifier",
            description="Improved logistic regression model with enhanced features",
            tags={
                "team": "nlp",
                "domain": "sentiment_analysis", 
                "algorithm": "logistic_regression",
                "improvement": "enhanced_features"
            },
            owner="ml-team",
            use_case="news_sentiment_analysis",
            performance_metrics={"accuracy": accuracy, "f1_score": f1},
            deployment_target="production"
        )
        
        improved_version = registry.register_model(
            model_uri=f"runs:/{run.info.run_id}/model",
            name="neuro_sentiment_classifier",
            metadata=improved_metadata
        )
        
        print(f"✅ Registered improved model: v{improved_version.version}")
        
        # Compare the two versions
        print(f"\n📊 Comparing model versions...")
        comparison = registry.compare_model_versions(
            name="neuro_sentiment_classifier",
            version1="1",
            version2=improved_version.version
        )
        
        if comparison:
            print(f"📈 Comparison Results:")
            print(f"   Model: {comparison['model_name']}")
            print(f"   Version 1 (baseline):")
            for metric, value in comparison['version1']['metrics'].items():
                print(f"     {metric}: {value:.4f}")
            print(f"   Version {improved_version.version} (improved):")
            for metric, value in comparison['version2']['metrics'].items():
                print(f"     {metric}: {value:.4f}")
            print(f"   Improvements:")
            for metric, changes in comparison['improvements'].items():
                print(f"     {metric}: {changes['relative_change']:+.2f}% ({changes['absolute_change']:+.4f})")


def demonstrate_deployment_management():
    """Demonstrate deployment management features."""
    print("\n" + "="*60)
    print("🚀 DEPLOYMENT MANAGEMENT DEMO")  
    print("="*60)
    
    registry = setup_model_registry()
    
    # Get deployment info for sentiment model
    print(f"\n📋 Getting deployment information...")
    
    deployment_info = registry.get_model_deployment_info("neuro_sentiment_classifier")
    
    if deployment_info:
        print(f"🎯 Deployment Status for {deployment_info['model_name']}:")
        
        if deployment_info['production']['version']:
            print(f"   Production: v{deployment_info['production']['version']}")
            print(f"     URI: {deployment_info['production']['model_uri']}")
        else:
            print(f"   Production: No version deployed")
        
        if deployment_info['staging']:
            print(f"   Staging: {len(deployment_info['staging'])} version(s)")
            for staging in deployment_info['staging']:
                print(f"     v{staging['version']}: {staging['model_uri']}")
        else:
            print(f"   Staging: No versions")
        
        if deployment_info['latest']['version']:
            print(f"   Latest: v{deployment_info['latest']['version']} ({deployment_info['latest']['stage']})")
            print(f"     URI: {deployment_info['latest']['model_uri']}")
    
    # Demonstrate production model URI retrieval
    print(f"\n🔗 Getting production model URI...")
    production_uri = get_production_model_uri("neuro_sentiment_classifier")
    
    if production_uri:
        print(f"✅ Production model URI: {production_uri}")
        print(f"   Use this URI to load the production model:")
        print(f"   model = mlflow.pyfunc.load_model('{production_uri}')")
    else:
        print(f"❌ No production model available")
    
    # Archive old versions
    print(f"\n🗄️  Archiving old model versions...")
    archived = registry.archive_old_versions(
        name="neuro_sentiment_classifier",
        keep_latest_n=2,
        exclude_production=True
    )
    
    if archived:
        print(f"✅ Archived versions: {archived}")
    else:
        print(f"ℹ️  No versions archived (keeping latest 2)")


def demonstrate_model_listing():
    """Demonstrate listing all models."""
    print("\n" + "="*60)
    print("📋 MODEL LISTING DEMO")
    print("="*60)
    
    print(f"\n📊 All registered models:")
    
    all_models = list_all_models()
    
    if all_models:
        for model_name, model_info in all_models.items():
            print(f"\n🤖 {model_name}")
            print(f"   Description: {model_info['description']}")
            print(f"   Versions:")
            
            for version in model_info['latest_versions']:
                print(f"     v{version['version']}: {version['stage']}")
            
            if model_info['tags']:
                print(f"   Tags: {', '.join(f'{k}={v}' for k, v in model_info['tags'].items())}")
    else:
        print(f"❌ No registered models found")


def demonstrate_helper_functions():
    """Demonstrate convenience helper functions."""
    print("\n" + "="*60)
    print("🔧 HELPER FUNCTIONS DEMO")
    print("="*60)
    
    # Simulate training a simple model for helper demo
    print(f"\n🏃‍♂️ Training simple model for helper demo...")
    
    X, y = make_classification(
        n_samples=500,
        n_features=10,
        n_classes=2,
        random_state=456
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=456
    )
    
    with mlrun(
        name="simple_model_helper_demo",
        experiment="research_prototypes",
        tags={
            "data_version": "v1.0.0",
            "notes": "Simple model for testing helper functions",
            "model_type": "random_forest",
            "task_type": "classification"
        }
    ) as run:
        model = RandomForestClassifier(n_estimators=50, random_state=456)
        model.fit(X_train, y_train)
        
        y_pred = model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        mlflow.log_param("n_estimators", 50)
        mlflow.log_metric("accuracy", accuracy)
        
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="model",
            input_example=X_test[:3]
        )
        
        simple_run_id = run.info.run_id
        print(f"✅ Trained simple model (accuracy: {accuracy:.4f})")
    
    # Use helper function to register model
    print(f"\n📝 Using register_model_from_run helper...")
    
    simple_metadata = ModelMetadata(
        name="neuro_topic_extractor",
        description="Simple topic extraction model for demo purposes",
        tags={"team": "research", "status": "experimental"},
        owner="research-team",
        use_case="topic_extraction",
        performance_metrics={"accuracy": accuracy},
        deployment_target="research"
    )
    
    simple_version = register_model_from_run(
        run_id=simple_run_id,
        model_name="neuro_topic_extractor",
        metadata=simple_metadata
    )
    
    print(f"✅ Registered using helper: {simple_version.name} v{simple_version.version}")
    
    # Use helper to promote to production (should fail due to low accuracy)
    print(f"\n🚀 Attempting to promote using helper...")
    try:
        production_version = promote_to_production(
            model_name="neuro_topic_extractor",
            version=simple_version.version,
            check_performance=False  # Skip performance checks for demo
        )
        print(f"✅ Promoted to production: v{production_version.version}")
        
        # Get production URI using helper
        prod_uri = get_production_model_uri("neuro_topic_extractor")
        print(f"🔗 Production URI: {prod_uri}")
        
    except ValueError as e:
        print(f"❌ Promotion failed: {e}")


def main():
    """Run the complete MLflow Model Registry demonstration."""
    print("🎯 MLflow Model Registry Implementation Demo")
    print("=" * 80)
    print("Issue #221: Comprehensive model lifecycle management with")
    print("model registration, versioning, stage transitions, and deployment")
    
    try:
        # Setup
        setup_demo_environment()
        
        # Core demonstrations
        registered_models = demonstrate_model_registration()
        demonstrate_stage_transitions(registered_models)
        demonstrate_model_comparison()
        demonstrate_deployment_management()
        demonstrate_model_listing()
        demonstrate_helper_functions()
        
        # Summary
        print("\n" + "="*80)
        print("🎉 MODEL REGISTRY DEMO COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        print(f"\n📊 Features demonstrated:")
        print(f"   ✅ Model registration with metadata")
        print(f"   ✅ Stage transitions (None → Staging → Production)")
        print(f"   ✅ Performance gate validation")
        print(f"   ✅ Model version comparison")
        print(f"   ✅ Deployment management")
        print(f"   ✅ Model archival and cleanup")
        print(f"   ✅ Helper functions for common tasks")
        
        print(f"\n🏷️  Standard models supported:")
        for model_name, description in NeuroNewsModelRegistry.STANDARD_MODELS.items():
            print(f"   • {model_name}: {description}")
        
        print(f"\n🔗 View results in MLflow UI:")
        print(f"   mlflow ui --backend-store-uri {os.environ.get('MLFLOW_TRACKING_URI', 'file:./mlruns')}")
        print(f"   Navigate to Models tab to see registered models")
        
        print(f"\n📖 Documentation: services/mlops/registry.py")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
