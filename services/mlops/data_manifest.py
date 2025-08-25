"""
Data Manifest Generation for MLflow Reproducibility

Issue #222: Generates dataset manifests with file hashes and sizes
for MLflow runs to ensure data reproducibility and integrity.

This module provides functionality to:
- Generate file hashes (MD5, SHA256) for datasets
- Create manifest files with metadata
- Log manifests as MLflow artifacts
- Validate data integrity against manifests

Usage:
    from services.mlops.data_manifest import DataManifestGenerator
    
    generator = DataManifestGenerator()
    manifest = generator.generate_manifest("/path/to/data")
    generator.log_to_mlflow(manifest)
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import logging

import mlflow


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataManifestGenerator:
    """
    Generator for data manifests with file hashes and metadata.
    """
    
    def __init__(self, hash_algorithms: Optional[List[str]] = None):
        """
        Initialize the manifest generator.
        
        Args:
            hash_algorithms: List of hash algorithms to use (default: ['md5', 'sha256'])
        """
        self.hash_algorithms = hash_algorithms or ['md5', 'sha256']
        self.supported_algorithms = ['md5', 'sha1', 'sha256', 'sha512']
        
        # Validate hash algorithms
        for algo in self.hash_algorithms:
            if algo not in self.supported_algorithms:
                raise ValueError(f"Unsupported hash algorithm: {algo}")
    
    def calculate_file_hash(self, file_path: Path, algorithm: str = 'md5') -> str:
        """
        Calculate hash for a file.
        
        Args:
            file_path: Path to the file
            algorithm: Hash algorithm to use
            
        Returns:
            Hexadecimal hash string
        """
        if algorithm not in self.supported_algorithms:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
            
        hash_func = hashlib.new(algorithm)
        
        try:
            with open(file_path, 'rb') as f:
                # Read file in chunks to handle large files efficiently
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hash_func.update(chunk)
                    
            return hash_func.hexdigest()
            
        except Exception as e:
            logger.error(f"Failed to calculate {algorithm} hash for {file_path}: {e}")
            raise
    
    def get_file_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Get comprehensive metadata for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with file metadata
        """
        try:
            stat = file_path.stat()
            
            metadata = {
                "path": str(file_path),
                "relative_path": str(file_path.relative_to(file_path.anchor)),
                "name": file_path.name,
                "size_bytes": stat.st_size,
                "size_human": self._format_size(stat.st_size),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created_time": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "permissions": oct(stat.st_mode)[-3:],
                "is_directory": file_path.is_dir(),
                "is_file": file_path.is_file(),
                "is_symlink": file_path.is_symlink()
            }
            
            # Calculate hashes for files (not directories)
            if file_path.is_file():
                metadata["hashes"] = {}
                for algorithm in self.hash_algorithms:
                    try:
                        metadata["hashes"][algorithm] = self.calculate_file_hash(file_path, algorithm)
                    except Exception as e:
                        logger.warning(f"Failed to calculate {algorithm} for {file_path}: {e}")
                        metadata["hashes"][algorithm] = None
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get metadata for {file_path}: {e}")
            raise
    
    def _format_size(self, size_bytes: int) -> str:
        """
        Format file size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def scan_directory(self, directory_path: Union[str, Path], 
                      include_patterns: Optional[List[str]] = None,
                      exclude_patterns: Optional[List[str]] = None,
                      max_files: Optional[int] = None) -> List[Path]:
        """
        Scan directory for files matching patterns.
        
        Args:
            directory_path: Path to directory to scan
            include_patterns: List of patterns to include (glob patterns)
            exclude_patterns: List of patterns to exclude (glob patterns)
            max_files: Maximum number of files to process
            
        Returns:
            List of file paths
        """
        directory_path = Path(directory_path)
        
        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")
            
        if not directory_path.is_dir():
            raise ValueError(f"Path is not a directory: {directory_path}")
        
        files = []
        
        # Default patterns
        if include_patterns is None:
            include_patterns = ['**/*']  # Include all files
            
        if exclude_patterns is None:
            exclude_patterns = [
                '**/.git/**', '**/__pycache__/**', '**/.pytest_cache/**',
                '**/*.pyc', '**/*.pyo', '**/.DS_Store', '**/Thumbs.db'
            ]
        
        # Collect files based on include patterns
        for pattern in include_patterns:
            for file_path in directory_path.glob(pattern):
                if file_path.is_file():
                    # Check if file should be excluded
                    should_exclude = False
                    for exclude_pattern in exclude_patterns:
                        if file_path.match(exclude_pattern):
                            should_exclude = True
                            break
                    
                    if not should_exclude:
                        files.append(file_path)
        
        # Remove duplicates and sort
        files = sorted(list(set(files)))
        
        # Limit number of files if specified
        if max_files and len(files) > max_files:
            logger.warning(f"Limiting to {max_files} files (found {len(files)})")
            files = files[:max_files]
        
        return files
    
    def generate_manifest(self, data_path: Union[str, Path],
                         include_patterns: Optional[List[str]] = None,
                         exclude_patterns: Optional[List[str]] = None,
                         max_files: Optional[int] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a complete data manifest for a directory or file.
        
        Args:
            data_path: Path to data directory or file
            include_patterns: List of patterns to include
            exclude_patterns: List of patterns to exclude
            max_files: Maximum number of files to process
            metadata: Additional metadata to include
            
        Returns:
            Complete manifest dictionary
        """
        data_path = Path(data_path)
        start_time = datetime.now()
        
        logger.info(f"🔍 Generating data manifest for: {data_path}")
        
        # Initialize manifest
        manifest = {
            "manifest_version": "1.0",
            "generated_at": start_time.isoformat(),
            "generator": "NeuroNews DataManifestGenerator",
            "data_path": str(data_path.absolute()),
            "hash_algorithms": self.hash_algorithms,
            "files": [],
            "summary": {},
            "metadata": metadata or {}
        }
        
        # Handle single file vs directory
        if data_path.is_file():
            files = [data_path]
        elif data_path.is_dir():
            files = self.scan_directory(
                data_path, include_patterns, exclude_patterns, max_files
            )
        else:
            raise ValueError(f"Invalid data path: {data_path}")
        
        logger.info(f"📁 Processing {len(files)} files...")
        
        # Process files
        total_size = 0
        processed_count = 0
        
        for file_path in files:
            try:
                file_metadata = self.get_file_metadata(file_path)
                
                # Make paths relative to data_path for consistency
                if data_path.is_dir():
                    try:
                        relative_path = file_path.relative_to(data_path)
                        file_metadata["relative_path"] = str(relative_path)
                    except ValueError:
                        # File is not under data_path
                        pass
                
                manifest["files"].append(file_metadata)
                
                if file_path.is_file():
                    total_size += file_metadata["size_bytes"]
                
                processed_count += 1
                
                if processed_count % 100 == 0:
                    logger.info(f"  📄 Processed {processed_count}/{len(files)} files...")
                    
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                # Add error entry
                manifest["files"].append({
                    "path": str(file_path),
                    "error": str(e),
                    "processed_at": datetime.now().isoformat()
                })
        
        # Generate summary
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        manifest["summary"] = {
            "total_files": len(files),
            "processed_files": processed_count,
            "total_size_bytes": total_size,
            "total_size_human": self._format_size(total_size),
            "processing_time_seconds": processing_time,
            "files_per_second": processed_count / processing_time if processing_time > 0 else 0,
            "average_file_size_bytes": total_size / processed_count if processed_count > 0 else 0,
            "hash_algorithms_used": self.hash_algorithms
        }
        
        logger.info(f"✅ Manifest generation complete!")
        logger.info(f"📊 Summary:")
        logger.info(f"   • {processed_count} files processed")
        logger.info(f"   • {self._format_size(total_size)} total size")
        logger.info(f"   • {processing_time:.1f}s processing time")
        
        return manifest
    
    def save_manifest(self, manifest: Dict[str, Any], output_path: Union[str, Path]) -> Path:
        """
        Save manifest to a JSON file.
        
        Args:
            manifest: Manifest dictionary
            output_path: Path to save the manifest
            
        Returns:
            Path to saved manifest file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, 'w') as f:
                json.dump(manifest, f, indent=2, default=str)
            
            logger.info(f"💾 Manifest saved to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to save manifest to {output_path}: {e}")
            raise
    
    def log_to_mlflow(self, manifest: Dict[str, Any], artifact_path: str = "data_manifest") -> None:
        """
        Log manifest to MLflow as an artifact.
        
        Args:
            manifest: Manifest dictionary
            artifact_path: MLflow artifact path
        """
        try:
            # Save manifest to temporary file
            temp_path = Path("/tmp/data_manifest.json")
            self.save_manifest(manifest, temp_path)
            
            # Log to MLflow
            mlflow.log_artifact(str(temp_path), artifact_path)
            
            # Log summary metrics
            summary = manifest["summary"]
            mlflow.log_metric("data_files_count", summary["processed_files"])
            mlflow.log_metric("data_size_bytes", summary["total_size_bytes"])
            mlflow.log_metric("data_processing_time", summary["processing_time_seconds"])
            
            # Log parameters
            mlflow.log_param("data_path", manifest["data_path"])
            mlflow.log_param("hash_algorithms", ",".join(manifest["hash_algorithms"]))
            mlflow.log_param("manifest_version", manifest["manifest_version"])
            
            logger.info(f"📊 Manifest logged to MLflow at: {artifact_path}")
            
            # Clean up temp file
            temp_path.unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"Failed to log manifest to MLflow: {e}")
            raise
    
    def validate_manifest(self, manifest: Dict[str, Any], data_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Validate data against a manifest.
        
        Args:
            manifest: Manifest dictionary to validate against
            data_path: Path to data to validate (uses manifest path if not provided)
            
        Returns:
            Validation results dictionary
        """
        if data_path is None:
            data_path = manifest["data_path"]
            
        data_path = Path(data_path)
        logger.info(f"🔍 Validating data against manifest...")
        
        validation_results = {
            "valid": True,
            "timestamp": datetime.now().isoformat(),
            "data_path": str(data_path),
            "manifest_files": len(manifest["files"]),
            "found_files": 0,
            "missing_files": [],
            "modified_files": [],
            "hash_mismatches": [],
            "size_mismatches": [],
            "errors": []
        }
        
        for file_info in manifest["files"]:
            if "error" in file_info:
                continue  # Skip files that had errors during manifest generation
                
            file_path = Path(file_info["relative_path"]) if "relative_path" in file_info else Path(file_info["path"])
            
            # Make absolute path
            if not file_path.is_absolute():
                full_path = data_path / file_path
            else:
                full_path = file_path
            
            # Check if file exists
            if not full_path.exists():
                validation_results["missing_files"].append(str(file_path))
                validation_results["valid"] = False
                continue
            
            validation_results["found_files"] += 1
            
            try:
                # Check file size
                current_size = full_path.stat().st_size
                if current_size != file_info["size_bytes"]:
                    validation_results["size_mismatches"].append({
                        "file": str(file_path),
                        "expected": file_info["size_bytes"],
                        "actual": current_size
                    })
                    validation_results["valid"] = False
                
                # Check modification time
                current_mtime = datetime.fromtimestamp(full_path.stat().st_mtime).isoformat()
                if current_mtime != file_info["modified_time"]:
                    validation_results["modified_files"].append({
                        "file": str(file_path),
                        "expected": file_info["modified_time"],
                        "actual": current_mtime
                    })
                
                # Validate hashes
                if "hashes" in file_info and file_info["hashes"]:
                    for algorithm, expected_hash in file_info["hashes"].items():
                        if expected_hash is None:
                            continue
                            
                        try:
                            actual_hash = self.calculate_file_hash(full_path, algorithm)
                            if actual_hash != expected_hash:
                                validation_results["hash_mismatches"].append({
                                    "file": str(file_path),
                                    "algorithm": algorithm,
                                    "expected": expected_hash,
                                    "actual": actual_hash
                                })
                                validation_results["valid"] = False
                        except Exception as e:
                            validation_results["errors"].append({
                                "file": str(file_path),
                                "error": f"Hash validation failed: {e}"
                            })
                
            except Exception as e:
                validation_results["errors"].append({
                    "file": str(file_path),
                    "error": str(e)
                })
                validation_results["valid"] = False
        
        # Summary
        logger.info(f"📊 Validation complete:")
        logger.info(f"   • Valid: {validation_results['valid']}")
        logger.info(f"   • Found files: {validation_results['found_files']}/{validation_results['manifest_files']}")
        logger.info(f"   • Missing files: {len(validation_results['missing_files'])}")
        logger.info(f"   • Modified files: {len(validation_results['modified_files'])}")
        logger.info(f"   • Hash mismatches: {len(validation_results['hash_mismatches'])}")
        
        return validation_results


def generate_data_manifest_cli():
    """
    Command-line interface for data manifest generation.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate data manifest for MLflow reproducibility")
    parser.add_argument("data_path", help="Path to data directory or file")
    parser.add_argument("--output", "-o", help="Output manifest file path", default="data_manifest.json")
    parser.add_argument("--include", nargs="*", help="Include patterns (glob)")
    parser.add_argument("--exclude", nargs="*", help="Exclude patterns (glob)")
    parser.add_argument("--max-files", type=int, help="Maximum number of files to process")
    parser.add_argument("--hash-algorithms", nargs="*", default=["md5", "sha256"], 
                       help="Hash algorithms to use")
    parser.add_argument("--mlflow", action="store_true", help="Log to MLflow")
    parser.add_argument("--validate", help="Validate against existing manifest file")
    
    args = parser.parse_args()
    
    try:
        generator = DataManifestGenerator(hash_algorithms=args.hash_algorithms)
        
        if args.validate:
            # Validation mode
            with open(args.validate, 'r') as f:
                manifest = json.load(f)
            
            results = generator.validate_manifest(manifest, args.data_path)
            
            print(f"Validation {'PASSED' if results['valid'] else 'FAILED'}")
            if not results['valid']:
                print(f"Issues found:")
                if results['missing_files']:
                    print(f"  Missing files: {len(results['missing_files'])}")
                if results['hash_mismatches']:
                    print(f"  Hash mismatches: {len(results['hash_mismatches'])}")
                if results['size_mismatches']:
                    print(f"  Size mismatches: {len(results['size_mismatches'])}")
            
        else:
            # Generation mode
            manifest = generator.generate_manifest(
                args.data_path,
                include_patterns=args.include,
                exclude_patterns=args.exclude,
                max_files=args.max_files
            )
            
            generator.save_manifest(manifest, args.output)
            
            if args.mlflow:
                generator.log_to_mlflow(manifest)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(generate_data_manifest_cli())
