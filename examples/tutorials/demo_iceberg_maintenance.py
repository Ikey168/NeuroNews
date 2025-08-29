"""
Demo script for Iceberg table maintenance
Issue #293

Demonstrates the table maintenance operations:
1. Compaction (data files and manifests)
2. Snapshot expiration

This script can be used to test the maintenance operations locally.
"""
import subprocess
import sys
import os
from datetime import datetime, timedelta

def run_command(command, description):
    """Run a command and show the output."""
    print(f"\n🔄 {description}")
    print(f"Command: {command}")
    print("-" * 60)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode != 0:
            print(f"❌ Command failed with return code: {result.returncode}")
            return False
        else:
            print("✅ Command completed successfully")
            return True
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def main():
    """Run demo of table maintenance operations."""
    print("🧹 Iceberg Table Maintenance Demo")
    print("=" * 50)
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    spark_jobs_dir = os.path.join(script_dir, "airflow", "dags", "spark_jobs")
    
    # Table to maintain
    table_name = "demo.news.articles_enriched"
    
    # Calculate timestamp for expiration (7 days ago)
    expire_before = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"Table: {table_name}")
    print(f"Expire snapshots before: {expire_before}")
    
    # 1. Run data file compaction
    compaction_script = os.path.join(spark_jobs_dir, "iceberg_compaction.py")
    success1 = run_command(
        f"python {compaction_script} --table {table_name} --operation rewrite_data_files",
        "Data file compaction"
    )
    
    # 2. Run manifest compaction
    success2 = run_command(
        f"python {compaction_script} --table {table_name} --operation rewrite_manifests",
        "Manifest compaction"
    )
    
    # 3. Run snapshot expiration
    expiration_script = os.path.join(spark_jobs_dir, "iceberg_snapshot_expiration.py")
    success3 = run_command(
        f"python {expiration_script} --table {table_name} --older_than \"{expire_before}\" --retain_last 5",
        "Snapshot expiration"
    )
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Maintenance Demo Summary")
    print(f"✅ Data file compaction: {'SUCCESS' if success1 else 'FAILED'}")
    print(f"✅ Manifest compaction: {'SUCCESS' if success2 else 'FAILED'}")
    print(f"✅ Snapshot expiration: {'SUCCESS' if success3 else 'FAILED'}")
    
    if all([success1, success2, success3]):
        print("\n🎉 All maintenance operations completed successfully!")
        return 0
    else:
        print("\n❌ Some maintenance operations failed. Check logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
