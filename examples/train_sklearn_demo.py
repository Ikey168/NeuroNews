#!/usr/bin/env python3
"""
MLflow Autologging Demo with Scikit-Learn
Issue #219: Autologging demo (sklearn) + template notebook

This script demonstrates MLflow's autolo    # Log classification report as artifact
    try:
        report = classification_report(y_test_clf, y_pred, output_dict=True)
        mlflow.log_dict(report, "classification_report.json")
    except Exception as e:
        print(f"⚠️  Warning: Could not log classification report: {e}")
    
    print(f"✅ Logistic Regression - Test Accuracy: {accuracy:.4f}") capabilities with scikit-learn
by training a simple logistic regression model on toy data and automatically
logging parameters, metrics, and model artifacts.

Usage:
    python examples/train_sklearn_demo.py

Environment Variables:
    MLFLOW_TRACKING_URI: MLflow tracking server URI (default: http://localhost:5001)
    MLFLOW_EXPERIMENT_NAME: Experiment name (default: sklearn-autolog-demo)

Example:
    MLFLOW_TRACKING_URI=http://localhost:5001 python examples/train_sklearn_demo.py
"""

import os
import sys
import warnings
from datetime import datetime
from typing import Tuple, Dict, Any

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.datasets import make_classification, make_regression
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.metrics import accuracy_score, classification_report, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

# Suppress sklearn warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)


def setup_mlflow() -> None:
    """Setup MLflow tracking configuration."""
    # Set tracking URI from environment or use local file-based tracking
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
    mlflow.set_tracking_uri(tracking_uri)
    
    # Set experiment name
    experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "sklearn-autolog-demo")
    
    try:
        mlflow.set_experiment(experiment_name)
        print(f"✅ MLflow experiment set: {experiment_name}")
        print(f"🔗 Tracking URI: {tracking_uri}")
        if tracking_uri.startswith("file:"):
            print("📁 Using local file-based tracking (no server required)")
        else:
            print("🌐 Using MLflow tracking server")
    except Exception as e:
        print(f"❌ Failed to set MLflow experiment: {e}")
        if not tracking_uri.startswith("file:"):
            print("💡 Make sure MLflow server is running or use local tracking")
            print("   For local tracking: unset MLFLOW_TRACKING_URI")
        sys.exit(1)


def create_classification_dataset(n_samples: int = 1000, random_state: int = 42) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Create a synthetic classification dataset.
    
    Args:
        n_samples: Number of samples to generate
        random_state: Random seed for reproducibility
        
    Returns:
        Tuple of (features DataFrame, target Series)
    """
    X, y = make_classification(
        n_samples=n_samples,
        n_features=10,
        n_informative=5,
        n_redundant=2,
        n_clusters_per_class=1,
        random_state=random_state,
        class_sep=1.0
    )
    
    # Create feature names
    feature_names = [f"feature_{i+1}" for i in range(X.shape[1])]
    
    # Convert to DataFrame for better MLflow logging
    X_df = pd.DataFrame(X, columns=feature_names)
    y_series = pd.Series(y, name="target")
    
    return X_df, y_series


def create_regression_dataset(n_samples: int = 1000, random_state: int = 42) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Create a synthetic regression dataset.
    
    Args:
        n_samples: Number of samples to generate
        random_state: Random seed for reproducibility
        
    Returns:
        Tuple of (features DataFrame, target Series)
    """
    X, y = make_regression(
        n_samples=n_samples,
        n_features=8,
        n_informative=5,
        noise=0.1,
        random_state=random_state
    )
    
    # Create feature names
    feature_names = [f"feature_{i+1}" for i in range(X.shape[1])]
    
    # Convert to DataFrame for better MLflow logging
    X_df = pd.DataFrame(X, columns=feature_names)
    y_series = pd.Series(y, name="target")
    
    return X_df, y_series


def train_logistic_regression(X_train: pd.DataFrame, X_test: pd.DataFrame, 
                            y_train: pd.Series, y_test: pd.Series) -> Dict[str, Any]:
    """
    Train a logistic regression model with MLflow autologging.
    
    Args:
        X_train, X_test: Training and test features
        y_train, y_test: Training and test targets
        
    Returns:
        Dictionary with training results
    """
    print("\n🚀 Training Logistic Regression with Pipeline...")
    
    # Create pipeline with preprocessing and model
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(
            random_state=42,
            max_iter=1000,
            C=1.0,
            solver='liblinear'
        ))
    ])
    
    # Train the model (MLflow autologging will capture everything)
    pipeline.fit(X_train, y_train)
    
    # Make predictions
    y_pred = pipeline.predict(X_test)
    y_pred_proba = pipeline.predict_proba(X_test)
    
    # Calculate metrics
    accuracy = accuracy_score(y_test, y_pred)
    
    # Log additional custom metrics
    mlflow.log_metric("test_accuracy", accuracy)
    mlflow.log_metric("n_features", X_train.shape[1])
    mlflow.log_metric("train_samples", len(X_train))
    mlflow.log_metric("test_samples", len(X_test))
    
    # Log classification report as artifact
    report = classification_report(y_test, y_pred, output_dict=True)
    mlflow.log_dict(report, "classification_report.json")
    
    print(f"✅ Logistic Regression - Test Accuracy: {accuracy:.4f}")
    
    return {
        "model": pipeline,
        "accuracy": accuracy,
        "predictions": y_pred,
        "probabilities": y_pred_proba
    }


def train_random_forest(X_train: pd.DataFrame, X_test: pd.DataFrame, 
                       y_train: pd.Series, y_test: pd.Series) -> Dict[str, Any]:
    """
    Train a random forest model with MLflow autologging.
    
    Args:
        X_train, X_test: Training and test features
        y_train, y_test: Training and test targets
        
    Returns:
        Dictionary with training results
    """
    print("\n🌲 Training Random Forest...")
    
    # Create model
    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2
    )
    
    # Train the model
    model.fit(X_train, y_train)
    
    # Make predictions
    y_pred = model.predict(X_test)
    
    # Calculate metrics
    accuracy = accuracy_score(y_test, y_pred)
    
    # Log additional metrics
    mlflow.log_metric("test_accuracy", accuracy)
    mlflow.log_metric("feature_importances_std", np.std(model.feature_importances_))
    
    # Log feature importances
    feature_importance_df = pd.DataFrame({
        'feature': X_train.columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    try:
        mlflow.log_dict(feature_importance_df.to_dict('records'), "feature_importances.json")
    except Exception as e:
        print(f"⚠️  Warning: Could not log feature importances: {e}")
    
    print(f"✅ Random Forest - Test Accuracy: {accuracy:.4f}")
    
    return {
        "model": model,
        "accuracy": accuracy,
        "predictions": y_pred,
        "feature_importances": model.feature_importances_
    }


def train_linear_regression(X_train: pd.DataFrame, X_test: pd.DataFrame, 
                          y_train: pd.Series, y_test: pd.Series) -> Dict[str, Any]:
    """
    Train a linear regression model with MLflow autologging.
    
    Args:
        X_train, X_test: Training and test features
        y_train, y_test: Training and test targets
        
    Returns:
        Dictionary with training results
    """
    print("\n📈 Training Linear Regression with Pipeline...")
    
    # Create pipeline
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('regressor', LinearRegression())
    ])
    
    # Train the model
    pipeline.fit(X_train, y_train)
    
    # Make predictions
    y_pred = pipeline.predict(X_test)
    
    # Calculate metrics
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    # Log additional metrics
    mlflow.log_metric("test_mse", mse)
    mlflow.log_metric("test_r2", r2)
    mlflow.log_metric("test_rmse", np.sqrt(mse))
    
    print(f"✅ Linear Regression - Test R²: {r2:.4f}, RMSE: {np.sqrt(mse):.4f}")
    
    return {
        "model": pipeline,
        "mse": mse,
        "r2": r2,
        "predictions": y_pred
    }


def demonstration_run():
    """Run the complete MLflow autologging demonstration."""
    print("🎯 MLflow Autologging Demo with Scikit-Learn")
    print("=" * 50)
    
    # Setup MLflow
    setup_mlflow()
    
    # Enable sklearn autologging
    print("\n🔄 Enabling MLflow sklearn autologging...")
    mlflow.sklearn.autolog(
        log_input_examples=True,
        log_model_signatures=True,
        log_models=True,
        log_datasets=True,
        disable=False,
        exclusive=False,
        disable_for_unsupported_versions=False,
        silent=False
    )
    print("✅ Autologging enabled!")
    
    # Run classification examples
    print("\n" + "="*50)
    print("🎯 CLASSIFICATION EXAMPLES")
    print("="*50)
    
    # Create classification dataset
    X_clf, y_clf = create_classification_dataset(n_samples=1500, random_state=42)
    X_train_clf, X_test_clf, y_train_clf, y_test_clf = train_test_split(
        X_clf, y_clf, test_size=0.2, random_state=42, stratify=y_clf
    )
    
    print(f"📊 Classification Dataset: {X_clf.shape[0]} samples, {X_clf.shape[1]} features")
    print(f"🔀 Train/Test Split: {len(X_train_clf)}/{len(X_test_clf)} samples")
    
    # Train models with autologging
    results = {}
    
    # Logistic Regression
    with mlflow.start_run(run_name=f"logistic_regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        mlflow.set_tag("model_type", "logistic_regression")
        mlflow.set_tag("task_type", "classification")
        mlflow.set_tag("dataset_type", "synthetic")
        results['logistic'] = train_logistic_regression(X_train_clf, X_test_clf, y_train_clf, y_test_clf)
    
    # Random Forest
    with mlflow.start_run(run_name=f"random_forest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        mlflow.set_tag("model_type", "random_forest")
        mlflow.set_tag("task_type", "classification")
        mlflow.set_tag("dataset_type", "synthetic")
        results['forest'] = train_random_forest(X_train_clf, X_test_clf, y_train_clf, y_test_clf)
    
    # Run regression example
    print("\n" + "="*50)
    print("📈 REGRESSION EXAMPLE")
    print("="*50)
    
    # Create regression dataset
    X_reg, y_reg = create_regression_dataset(n_samples=1200, random_state=42)
    X_train_reg, X_test_reg, y_train_reg, y_test_reg = train_test_split(
        X_reg, y_reg, test_size=0.2, random_state=42
    )
    
    print(f"📊 Regression Dataset: {X_reg.shape[0]} samples, {X_reg.shape[1]} features")
    print(f"🔀 Train/Test Split: {len(X_train_reg)}/{len(X_test_reg)} samples")
    
    # Linear Regression
    with mlflow.start_run(run_name=f"linear_regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
        mlflow.set_tag("model_type", "linear_regression")
        mlflow.set_tag("task_type", "regression")
        mlflow.set_tag("dataset_type", "synthetic")
        results['linear'] = train_linear_regression(X_train_reg, X_test_reg, y_train_reg, y_test_reg)
    
    # Summary
    print("\n" + "="*50)
    print("📊 TRAINING SUMMARY")
    print("="*50)
    print(f"✅ Logistic Regression Accuracy: {results['logistic']['accuracy']:.4f}")
    print(f"✅ Random Forest Accuracy: {results['forest']['accuracy']:.4f}")
    print(f"✅ Linear Regression R²: {results['linear']['r2']:.4f}")
    
    print(f"\n🎉 Demo completed successfully!")
    print(f"🔗 View results in MLflow UI: {mlflow.get_tracking_uri()}")
    
    # Get current experiment name
    try:
        current_experiment = mlflow.get_experiment_by_name(os.getenv("MLFLOW_EXPERIMENT_NAME", "sklearn-autolog-demo"))
        if current_experiment:
            print(f"📝 Experiment: {current_experiment.name}")
    except Exception:
        print(f"📝 Experiment: sklearn-autolog-demo")
    
    return results


if __name__ == "__main__":
    try:
        results = demonstration_run()
        print("\n✅ All models trained and logged successfully!")
    except Exception as e:
        print(f"\n❌ Error during training: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
