#!/usr/bin/env python3
"""
Cleanup script to free up disk space by removing unnecessary files and caches.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_size_format(bytes):
    """Convert bytes to human readable format"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0


def clean_pip_cache():
    """Clean pip cache"""
    try:
        logger.info("Cleaning pip cache...")
        subprocess.run(["pip", "cache", "purge"], check=True)
        logger.info("Pip cache cleaned successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error cleaning pip cache: {e}")


def clean_pytest_cache():
    """Remove pytest cache directories"""
    try:
        logger.info("Cleaning pytest cache...")
        for path in Path(".").rglob("__pycache__"):
            shutil.rmtree(path, ignore_errors=True)
        for path in Path(".").rglob(".pytest_cache"):
            shutil.rmtree(path, ignore_errors=True)
        logger.info("Pytest cache cleaned successfully")
    except Exception as e:
        logger.error(f"Error cleaning pytest cache: {e}")


def clean_build_artifacts():
    """Remove build artifacts and temporary files"""
    patterns_to_remove = [
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.so",
        "*.egg",
        "*.egg-info",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
        ".coverage",
        "htmlcov",
        ".tox",
    ]

    try:
        logger.info("Cleaning build artifacts...")
        for pattern in patterns_to_remove:
            for path in Path(".").rglob(pattern):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
        logger.info("Build artifacts cleaned successfully")
    except Exception as e:
        logger.error(f"Error cleaning build artifacts: {e}")


def get_directory_size(path):
    """Get the total size of a directory"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if not os.path.islink(file_path):
                total_size += os.path.getsize(file_path)
    return total_size


def main():
    """Main cleanup function"""
    logger.info("Starting cleanup process...")

    # Get initial disk usage
    initial_size = get_directory_size(".")
    logger.info(f"Initial project size: {get_size_format(initial_size)}")

    # Perform cleanup tasks
    clean_pip_cache()
    clean_pytest_cache()
    clean_build_artifacts()

    # Get final disk usage
    final_size = get_directory_size(".")
    space_saved = initial_size - final_size
    logger.info(f"Final project size: {get_size_format(final_size)}")
    logger.info(f"Total space saved: {get_size_format(space_saved)}")

    # Suggest additional cleanup if needed
    if space_saved < 1024 * 1024 * 100:  # If less than 100MB freed
        logger.info("\nAdditional cleanup suggestions:")
        logger.info("1. Run 'sudo apt-get clean' to clean package cache")
        logger.info("2. Run 'sudo apt-get autoremove' to remove unused packages")
        logger.info("3. Consider uninstalling large unused packages:")
        logger.info("   pip uninstall torch transformers (if not immediately needed)")


if __name__ == "__main__":
    main()
