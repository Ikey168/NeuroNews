#!/usr/bin/env python3
"""
Demo: Environment Capture and Data Manifest for Reproducibility

Issue #222: Demonstrates the reproducibility features including:
- Environment capture (pip freeze, system info, GPU/CPU details)
- Data manifest generation (file hashes, sizes, metadata)
- Integration with MLflow tracking

This script shows how to use the new reproducibility tools to ensure
experiments can be perfectly reproduced later.

Usage:
    python demo_reproducibility_features.py

Environment Variables:
    MLFLOW_TRACKING_URI: MLflow tracking server URI (default: file:./mlruns)

Example:
    MLFLOW_TRACKING_URI=http://localhost:5001 python demo_reproducibility_features.py
"""

import os
import sys
import tempfile
import json
from datetime import datetime
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from scripts.capture_env import capture_environment
    from services.mlops.data_manifest import DataManifestGenerator
    from services.mlops.tracking import mlrun
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running from the project root directory")
    sys.exit(1)


def setup_mlflow():
    """Setup MLflow tracking configuration."""
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
    mlflow.set_tracking_uri(tracking_uri)
    
    experiment_name = "reproducibility-demo"
    mlflow.set_experiment(experiment_name)
    
    print(f"✅ MLflow experiment set: {experiment_name}")
    print(f"🔗 Tracking URI: {tracking_uri}")


def create_sample_dataset():
    """Create a sample dataset for demonstration."""
    print("📊 Creating sample dataset...")
    
    # Create synthetic data
    np.random.seed(42)
    data = {
        'feature_1': np.random.normal(0, 1, 1000),
        'feature_2': np.random.exponential(2, 1000),
        'feature_3': np.random.uniform(-5, 5, 1000),
        'category': np.random.choice(['A', 'B', 'C'], 1000),
        'target': np.random.normal(10, 3, 1000)
    }
    
    df = pd.DataFrame(data)
    
    # Save to temporary directory for manifest generation
    temp_dir = Path("/tmp/demo_data")
    temp_dir.mkdir(exist_ok=True)
    
    # Save in multiple formats
    csv_path = temp_dir / "sample_data.csv"
    json_path = temp_dir / "sample_metadata.json"
    
    df.to_csv(csv_path, index=False)
    
    metadata = {
        "dataset_name": "Sample Demo Dataset",
        "created_at": datetime.now().isoformat(),
        "description": "Synthetic dataset for reproducibility demo",
        "features": list(df.columns),
        "shape": df.shape,
        "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "summary_stats": df.describe().to_dict()
    }
    
    with open(json_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print(f"✅ Dataset created: {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"📁 Saved to: {temp_dir}")
    
    return df, temp_dir, metadata


def demo_environment_capture():
    """Demonstrate environment capture functionality."""
    print("\n" + "="*60)
    print("🔍 DEMO: Environment Capture")
    print("="*60)
    
    output_dir = "/tmp/demo_env_capture"
    
    print("Capturing environment information...")
    artifacts = capture_environment(output_dir=output_dir, log_to_mlflow=False)
    
    print(f"\n📊 Environment Capture Results:")
    for name, path in artifacts.items():
        size = Path(path).stat().st_size
        print(f"   • {name}: {path} ({size} bytes)")
    
    # Show sample content
    if "requirements.txt" in artifacts:
        print(f"\n📦 Sample from requirements.txt:")
        with open(artifacts["requirements.txt"], 'r') as f:
            lines = f.readlines()[:5]
            for line in lines:
                print(f"     {line.strip()}")
            if len(lines) >= 5:
                print(f"     ... (and more)")
    
    if "system_info.json" in artifacts:
        print(f"\n💻 Sample from system_info.json:")
        with open(artifacts["system_info.json"], 'r') as f:
            data = json.load(f)
            print(f"     Python version: {data['python']['version']}")
            print(f"     OS: {data['platform']['system']} {data['platform']['release']}")
            print(f"     CPU cores: {data['cpu']['cpu_count']}")
            print(f"     GPUs: {len(data['gpu']['gpus'])}")
    
    return artifacts


def demo_data_manifest():
    """Demonstrate data manifest generation functionality."""
    print("\n" + "="*60)
    print("📋 DEMO: Data Manifest Generation")
    print("="*60)
    
    # Create sample dataset
    df, data_dir, metadata = create_sample_dataset()
    
    # Generate manifest
    generator = DataManifestGenerator(hash_algorithms=['md5', 'sha256'])
    
    print("Generating data manifest...")
    manifest = generator.generate_manifest(
        data_dir,
        metadata={
            "demo_run": "reproducibility_demo",
            "purpose": "Demonstrate data manifest generation",
            "timestamp": datetime.now().isoformat()
        }
    )
    
    # Save manifest
    manifest_path = data_dir / "data_manifest.json"
    generator.save_manifest(manifest, manifest_path)
    
    print(f"\n📊 Data Manifest Results:")
    print(f"   • Files processed: {manifest['summary']['processed_files']}")
    print(f"   • Total size: {manifest['summary']['total_size_human']}")
    print(f"   • Processing time: {manifest['summary']['processing_time_seconds']:.2f}s")
    print(f"   • Hash algorithms: {manifest['hash_algorithms']}")
    
    # Show sample file details
    if manifest['files']:
        sample_file = manifest['files'][0]
        print(f"\n📄 Sample file details:")
        print(f"   • Name: {sample_file['name']}")
        print(f"   • Size: {sample_file['size_human']}")
        if 'hashes' in sample_file:
            for algo, hash_val in sample_file['hashes'].items():
                print(f"   • {algo.upper()}: {hash_val[:16]}...")
    
    return manifest, data_dir


def demo_mlflow_integration():
    """Demonstrate MLflow integration with reproducibility features."""
    print("\n" + "="*60)
    print("📊 DEMO: MLflow Integration")
    print("="*60)
    
    with mlrun(
        name=f"reproducibility_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        experiment="reproducibility-demo",
        tags={
            "demo": "reproducibility", 
            "version": "1.0",
            "pipeline": "demo",
            "data_version": "1.0",
            "env": "development"
        }
    ) as run:
        
        # Capture environment
        print("🔍 Capturing environment...")
        try:
            env_artifacts = capture_environment(
                output_dir=f"/tmp/mlflow_env_{run.info.run_name}",
                log_to_mlflow=True
            )
            print(f"   ✅ Environment captured: {len(env_artifacts)} artifacts")
        except Exception as e:
            print(f"   ❌ Environment capture failed: {e}")
        
        # Create and manifest sample data
        print("📋 Creating data manifest...")
        try:
            df, data_dir, metadata = create_sample_dataset()
            
            generator = DataManifestGenerator()
            manifest = generator.generate_manifest(
                data_dir,
                metadata={
                    "mlflow_run": run.info.run_name,
                    "experiment": "reproducibility-demo"
                }
            )
            
            # Log manifest to MLflow
            generator.log_to_mlflow(manifest, "demo_data_manifest")
            print(f"   ✅ Data manifest logged to MLflow")
            
        except Exception as e:
            print(f"   ❌ Data manifest generation failed: {e}")
        
        # Log some demo metrics and parameters
        mlflow.log_param("demo_type", "reproducibility")
        mlflow.log_param("dataset_size", len(df))
        mlflow.log_param("features", df.shape[1])
        
        mlflow.log_metric("mean_target", df['target'].mean())
        mlflow.log_metric("std_target", df['target'].std())
        
        # Save a demo artifact
        demo_summary = {
            "demo_completed_at": datetime.now().isoformat(),
            "features_demonstrated": [
                "Environment capture",
                "Data manifest generation",
                "MLflow integration"
            ],
            "dataset_summary": {
                "rows": len(df),
                "columns": list(df.columns),
                "numeric_features": len(df.select_dtypes(include=[np.number]).columns),
                "categorical_features": len(df.select_dtypes(include=['object']).columns)
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(demo_summary, f, indent=2, default=str)
            mlflow.log_artifact(f.name, "demo_summary.json")
        
        print(f"\n📊 MLflow Run Info:")
        print(f"   • Run ID: {run.info.run_id}")
        print(f"   • Run Name: {run.info.run_name}")
        print(f"   • Experiment: {run.info.experiment_id}")
        
        return run.info


def demo_manifest_validation():
    """Demonstrate manifest validation functionality."""
    print("\n" + "="*60)
    print("🔍 DEMO: Manifest Validation")
    print("="*60)
    
    # Create and manifest data
    df, data_dir, metadata = create_sample_dataset()
    
    generator = DataManifestGenerator()
    original_manifest = generator.generate_manifest(data_dir)
    
    print("✅ Original manifest generated")
    
    # Validate against original data (should pass)
    print("\n🔍 Validating against original data...")
    validation_results = generator.validate_manifest(original_manifest, data_dir)
    
    print(f"   • Validation result: {'✅ PASSED' if validation_results['valid'] else '❌ FAILED'}")
    print(f"   • Files found: {validation_results['found_files']}/{validation_results['manifest_files']}")
    print(f"   • Missing files: {len(validation_results['missing_files'])}")
    print(f"   • Hash mismatches: {len(validation_results['hash_mismatches'])}")
    
    # Modify a file and validate again (should fail)
    print("\n🔧 Modifying a file and re-validating...")
    csv_file = data_dir / "sample_data.csv"
    
    # Append a line to modify the file
    with open(csv_file, 'a') as f:
        f.write("\n# This file has been modified\n")
    
    validation_results = generator.validate_manifest(original_manifest, data_dir)
    
    print(f"   • Validation result: {'✅ PASSED' if validation_results['valid'] else '❌ FAILED'}")
    print(f"   • Files found: {validation_results['found_files']}/{validation_results['manifest_files']}")
    print(f"   • Hash mismatches: {len(validation_results['hash_mismatches'])}")
    
    if validation_results['hash_mismatches']:
        mismatch = validation_results['hash_mismatches'][0]
        print(f"   • Detected change in: {mismatch['file']}")
        print(f"   • Algorithm: {mismatch['algorithm']}")
        print(f"   • Expected: {mismatch['expected'][:16]}...")
        print(f"   • Actual: {mismatch['actual'][:16]}...")


def main():
    """Run the complete reproducibility demo."""
    print("🎯 Reproducibility Features Demo")
    print("Issue #222: Environment Capture + Data Manifest")
    print("=" * 60)
    
    setup_mlflow()
    
    try:
        # Demo individual components
        demo_environment_capture()
        demo_data_manifest()
        demo_manifest_validation()
        
        # Demo MLflow integration
        run_info = demo_mlflow_integration()
        
        print("\n" + "="*60)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("="*60)
        
        print(f"\n📊 Summary:")
        print(f"   • Environment capture: ✅ Working")
        print(f"   • Data manifest generation: ✅ Working")
        print(f"   • Manifest validation: ✅ Working")
        print(f"   • MLflow integration: ✅ Working")
        print(f"\n🔗 MLflow Run: {run_info.run_id}")
        
        if mlflow.get_tracking_uri().startswith("file:"):
            print(f"💡 View results in MLflow UI:")
            print(f"   mlflow ui --backend-store-uri {mlflow.get_tracking_uri()}")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
