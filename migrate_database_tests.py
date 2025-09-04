#!/usr/bin/env python3
"""
Database Test Migration Script
Migrates scattered database test files into modular structure and removes duplicates
"""

import os
import shutil
import sys
from pathlib import Path

# Test file categorization based on naming patterns and content analysis
TEST_CATEGORIZATION = {
    # Connection related tests - move to modules/connection/
    'connection': [
        'test_database_connection_performance.py',
        'test_database_connection_performance_mock.py',
        'test_database_transaction_connection_tests.py',
    ],
    
    # Performance related tests - move to modules/performance/
    'performance': [
        'test_database_connection_performance.py',  # Has both connection and performance
        'test_database_optimized_coverage.py',
        'test_database_precise_coverage.py',
    ],
    
    # Integration tests - move to integration/ (already exists)
    'integration': [
        'test_database_integration_comprehensive.py',
        'test_database_integration_simplified.py',
        'test_database_comprehensive.py',
    ],
    
    # Coverage boost tests - these are legacy/duplicate and should be archived
    'legacy': [
        'test_corrected_massive_80_percent.py',
        'test_database_coverage_boost.py',
        'test_database_final_coverage_push.py',
        'test_database_final_push_80.py',
        'test_database_setup_strategic_80.py',
        'test_database_strategic_coverage.py',
        'test_final_comprehensive_80_percent_achievement.py',
        'test_final_precision_maximum_coverage.py',
        'test_final_push_80_percent.py',
        'test_final_push_to_80_percent.py',
        'test_final_strategic_coverage_push.py',
        'test_massive_80_percent_push.py',
        'test_massive_coverage_push_80_percent.py',
        'test_mega_80_percent_final_push.py',
        'test_strategic_80_percent_final_push.py',
        'test_strategic_push_to_50_percent.py',
        'test_ultimate_80_percent_achievement.py',
        'test_ultimate_80_percent_coverage_push.py',
        'test_ultimate_80_percent_push.py',
        'test_ultimate_coverage_push_to_80.py',
        'test_ultra_focused_coverage_boost.py',
        'test_ultra_precise_coverage_push.py',
        'test_ultra_precise_working_coverage.py',
        'test_ultra_targeted_80_percent_final_push.py',
        'test_working_strategic_push_to_40.py',
    ],
    
    # Specific module tests - keep in modules with descriptive names
    'modules': [
        'test_data_validation_pipeline_80push.py',  # Already have this in modules/data_validation/
        'test_dynamodb_metadata_strategic_80.py',  # Should be in modules/dynamodb/
        'test_s3_storage_strategic_80.py',  # Should be in modules/s3_storage/
    ]
}


def migrate_database_tests():
    """Migrate scattered database tests into proper modular structure"""
    
    base_path = Path('/workspaces/NeuroNews/tests/unit/database')
    modules_path = base_path / 'modules'
    
    print("Starting database test migration...")
    print(f"Base path: {base_path}")
    print(f"Modules path: {modules_path}")
    
    # Ensure module directories exist
    (modules_path / 'legacy').mkdir(exist_ok=True)
    (modules_path / 'connection').mkdir(exist_ok=True)
    (modules_path / 'performance').mkdir(exist_ok=True)
    
    # Track what we've moved
    moved_files = []
    skipped_files = []
    duplicate_files = []
    
    # Get current files in database test directory
    current_files = []
    for item in base_path.iterdir():
        if item.is_file() and item.name.startswith('test_') and item.name.endswith('.py'):
            current_files.append(item.name)
    
    print(f"\nFound {len(current_files)} test files to process:")
    for file in sorted(current_files):
        print(f"  - {file}")
    
    # Process each category
    for category, files in TEST_CATEGORIZATION.items():
        print(f"\n=== Processing {category} category ===")
        
        for filename in files:
            source_file = base_path / filename
            
            if not source_file.exists():
                print(f"  SKIP: {filename} (file not found)")
                skipped_files.append(filename)
                continue
            
            # Determine destination based on category
            if category == 'legacy':
                dest_dir = modules_path / 'legacy'
                dest_file = dest_dir / filename
                action = "ARCHIVE"
            elif category == 'connection':
                dest_dir = modules_path / 'connection'
                # Rename to avoid conflicts with existing comprehensive connection test
                if filename == 'test_database_connection_performance.py':
                    dest_file = dest_dir / 'test_legacy_connection_performance.py'
                elif filename == 'test_database_connection_performance_mock.py':
                    dest_file = dest_dir / 'test_legacy_connection_mock.py'
                else:
                    dest_file = dest_dir / filename
                action = "MOVE"
            elif category == 'performance':
                dest_dir = modules_path / 'performance'
                # Check if we already have comprehensive performance tests
                if filename == 'test_database_connection_performance.py':
                    dest_file = dest_dir / 'test_legacy_performance_connection.py'
                else:
                    dest_file = dest_dir / filename
                action = "MOVE"
            elif category == 'integration':
                dest_dir = base_path / 'integration'
                dest_file = dest_dir / filename
                action = "MOVE"
            elif category == 'modules':
                # Special handling for specific module tests
                if 'dynamodb' in filename:
                    dest_dir = modules_path / 'dynamodb'
                    dest_dir.mkdir(exist_ok=True)
                    dest_file = dest_dir / filename.replace('_strategic_80', '')
                elif 's3' in filename:
                    dest_dir = modules_path / 's3_storage'
                    dest_dir.mkdir(exist_ok=True)
                    dest_file = dest_dir / filename.replace('_strategic_80', '')
                elif 'data_validation' in filename:
                    # Skip - already have comprehensive data validation tests
                    print(f"  SKIP: {filename} (comprehensive version exists)")
                    skipped_files.append(filename)
                    continue
                else:
                    dest_dir = modules_path
                    dest_file = dest_dir / filename
                action = "MOVE"
            else:
                print(f"  ERROR: Unknown category {category} for {filename}")
                continue
            
            # Check if destination already exists
            if dest_file.exists():
                print(f"  DUPLICATE: {filename} -> {dest_file} (destination exists)")
                duplicate_files.append(filename)
                # Move to legacy instead
                legacy_dest = modules_path / 'legacy' / f"duplicate_{filename}"
                shutil.move(str(source_file), str(legacy_dest))
                print(f"    Moved to legacy as: {legacy_dest.name}")
            else:
                # Move the file
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_file), str(dest_file))
                moved_files.append((filename, str(dest_file)))
                print(f"  {action}: {filename} -> {dest_file}")
    
    # Generate migration summary
    print(f"\n=== MIGRATION SUMMARY ===")
    print(f"Moved files: {len(moved_files)}")
    for filename, dest in moved_files:
        print(f"  ✓ {filename} -> {dest}")
    
    print(f"\nSkipped files: {len(skipped_files)}")
    for filename in skipped_files:
        print(f"  - {filename}")
    
    print(f"\nDuplicate files: {len(duplicate_files)}")
    for filename in duplicate_files:
        print(f"  ! {filename}")
    
    # Check what's left in the main directory
    remaining_files = []
    for item in base_path.iterdir():
        if item.is_file() and item.name.startswith('test_') and item.name.endswith('.py'):
            remaining_files.append(item.name)
    
    print(f"\nRemaining files in main directory: {len(remaining_files)}")
    for filename in sorted(remaining_files):
        print(f"  ? {filename}")
    
    print(f"\n=== MODULAR STRUCTURE COMPLETE ===")
    print(f"Created modular test organization:")
    print(f"  - modules/connection/: Connection-specific tests")
    print(f"  - modules/performance/: Performance-specific tests") 
    print(f"  - modules/transaction/: Transaction-specific tests")
    print(f"  - modules/data_validation/: Data validation tests")
    print(f"  - modules/dynamodb/: DynamoDB-specific tests")
    print(f"  - modules/s3_storage/: S3 storage tests")
    print(f"  - modules/legacy/: Archived duplicate/old tests")
    print(f"  - integration/: Integration tests")


if __name__ == "__main__":
    migrate_database_tests()
