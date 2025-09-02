#!/usr/bin/env python3
"""
Demo script for NeuroNews MLflow tracking helper.

This script demonstrates how to use the mlrun context manager for standardized
ML experiment tracking with MLflow.
"""

import os
import sys
import time
import numpy as np
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.mlops.tracking import mlrun, setup_mlflow_env


def demo_sentiment_analysis():
    """Demo sentiment analysis experiment tracking."""
    print("🚀 Demo: Sentiment Analysis Experiment")
    
    # Simulate model training
    with mlrun("sentiment-bert-training", experiment="news-sentiment") as run:
        # Log hyperparameters
        mlflow.log_param("model_type", "bert-base-uncased")
        mlflow.log_param("learning_rate", 2e-5)
        mlflow.log_param("batch_size", 32)
        mlflow.log_param("epochs", 3)
        mlflow.log_param("dataset_size", 10000)
        
        # Simulate training metrics over epochs
        for epoch in range(3):
            # Simulate metrics getting better
            accuracy = 0.75 + (epoch * 0.08) + np.random.normal(0, 0.01)
            loss = 0.8 - (epoch * 0.25) + np.random.normal(0, 0.05)
            f1_score = 0.72 + (epoch * 0.09) + np.random.normal(0, 0.01)
            
            mlflow.log_metric("accuracy", accuracy, step=epoch)
            mlflow.log_metric("loss", loss, step=epoch)
            mlflow.log_metric("f1_score", f1_score, step=epoch)
            
            print(f"  Epoch {epoch}: acc={accuracy:.3f}, loss={loss:.3f}, f1={f1_score:.3f}")
            time.sleep(0.5)  # Simulate training time
        
        # Log final metrics
        mlflow.log_metric("final_accuracy", accuracy)
        mlflow.log_metric("final_f1_score", f1_score)
        
        # Create and log model artifact
        model_info = {
            "model_name": "sentiment-bert",
            "version": "1.0.0",
            "framework": "transformers",
            "performance": {
                "accuracy": accuracy,
                "f1_score": f1_score
            }
        }
        
        # Create temporary model file
        import json
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(model_info, f, indent=2)
            model_file = f.name
        
        mlflow.log_artifact(model_file, "model")
        os.unlink(model_file)  # Cleanup
        
        print(f"✅ Experiment completed! Run ID: {run.info.run_id}")


def demo_data_preprocessing():
    """Demo data preprocessing experiment tracking."""
    print("\n🔧 Demo: Data Preprocessing Pipeline")
    
    # Set pipeline context
    os.environ["NEURONEWS_PIPELINE"] = "data-preprocessing"
    
    with mlrun("news-data-preprocessing", tags={"pipeline_stage": "preprocessing"}) as run:
        # Log data processing parameters
        mlflow.log_param("source_format", "json")
        mlflow.log_param("target_format", "parquet")
        mlflow.log_param("text_cleaning", True)
        mlflow.log_param("sentiment_labeling", True)
        
        # Simulate data processing steps
        steps = [
            ("data_loading", 2.3),
            ("text_cleaning", 5.7),
            ("sentiment_labeling", 8.1),
            ("format_conversion", 1.9),
            ("validation", 0.8)
        ]
        
        total_records = 50000
        processed = 0
        
        for step_name, duration in steps:
            time.sleep(0.3)  # Simulate processing
            processed += total_records // len(steps)
            
            mlflow.log_metric(f"{step_name}_duration_seconds", duration)
            mlflow.log_metric("records_processed", processed)
            
            print(f"  {step_name}: {duration}s, processed {processed} records")
        
        # Log final statistics
        mlflow.log_metric("total_duration_seconds", sum(duration for _, duration in steps))
        mlflow.log_metric("total_records", total_records)
        mlflow.log_metric("processing_rate_records_per_second", total_records / sum(duration for _, duration in steps))
        
        print(f"✅ Data preprocessing completed! Run ID: {run.info.run_id}")


def demo_model_evaluation():
    """Demo model evaluation experiment tracking."""
    print("\n📊 Demo: Model Evaluation")
    
    with mlrun("sentiment-model-evaluation", 
               experiment="news-sentiment",
               tags={"evaluation_type": "holdout", "model_version": "v1.0"}) as run:
        
        # Log evaluation parameters
        mlflow.log_param("test_set_size", 2000)
        mlflow.log_param("evaluation_metrics", ["accuracy", "precision", "recall", "f1"])
        mlflow.log_param("threshold", 0.5)
        
        # Simulate evaluation metrics
        metrics = {
            "accuracy": 0.892,
            "precision": 0.887,
            "recall": 0.898,
            "f1_score": 0.892,
            "auc_roc": 0.945
        }
        
        for metric_name, value in metrics.items():
            mlflow.log_metric(metric_name, value)
            print(f"  {metric_name}: {value:.3f}")
        
        # Log confusion matrix data
        confusion_matrix = [[450, 38], [52, 460]]  # [[TN, FP], [FN, TP]]
        mlflow.log_param("confusion_matrix", str(confusion_matrix))
        
        print(f"✅ Model evaluation completed! Run ID: {run.info.run_id}")


def main():
    """Run all demos."""
    print("🧪 NeuroNews MLflow Tracking Helper Demo")
    print("=" * 50)
    
    # Setup MLflow environment
    setup_mlflow_env("http://localhost:5001", "neuronews-demo")
    
    try:
        # Import MLflow after setup
        import mlflow
        
        # Run demos
        demo_sentiment_analysis()
        demo_data_preprocessing()
        demo_model_evaluation()
        
        print("\n🎉 All demos completed successfully!")
        print("📊 View your experiments at: http://localhost:5001")
        print("\nTo run the demos:")
        print("1. Start MLflow: make mlflow-up")
        print("2. Run this script: python demo_tracking.py")
        print("3. Check the UI: make mlflow-ui")
        
    except ImportError:
        print("❌ MLflow not installed. Install with: pip install mlflow")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("Make sure MLflow server is running: make mlflow-up")
        sys.exit(1)


if __name__ == "__main__":
    main()
