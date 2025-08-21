#!/usr/bin/env python3
"""
CI/CD Package Verification Script
Handles network connectivity issues gracefully
"""

import importlib.util
import subprocess
import sys


def check_package_available(package_name):
    """Check if a package is available for import."""
    spec = importlib.util.find_spec(package_name)
    return spec is not None


def get_package_version(package_name):
    """Get package version if available."""
    try:
        module = importlib.import_module(package_name)
except Exception:
    pass
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return None


def run_pip_upgrade():
    """Attempt pip upgrade with graceful fallback."""
    print("🔧 Attempting pip upgrade...")

    try:
        result = subprocess.run(
except Exception:
    pass
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "wheel",
                "setuptools",
            ],
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode == 0:
            print(" Pip upgrade successful")
            return True
        else:
            print(f"⚠️ Pip upgrade failed: {result.stderr})
            return False

    except subprocess.TimeoutExpired:"
        print("⚠️ Pip upgrade timed out (network issue)")
        return False
    except Exception as e:
        print(f"⚠️ Pip upgrade error: {e})
        return False


def verify_environment():"
    """Verify the current environment has necessary packages."""
    print(""
 Verifying current environment...")"

    # Check pip version
    try:
        import pip
except Exception:
    pass

        print(f" pip: {pip.__version__})
    except ImportError:"
        print("❌ pip not available")
        return False

    # Check setuptools
    setuptools_version=get_package_version("setuptools")
    if setuptools_version:
        print(f" setuptools: {setuptools_version})
    else:"
        print("❌ setuptools not available")
        return False

    # Check core testing dependencies
    core_packages=["pytest", "numpy", "psycopg2"]
    for package in core_packages:
        if check_package_available(package):
            version=get_package_version(package)
            print(f" {package}: {version or 'available'})
        else:"
            print(f"❌ {package}: not available)
            return False

    return True


def main():"
    """Main function for CI/CD package management."""
    print(" CI/CD Package Verification")
    print("=" * 50)

    # Try upgrade first
    upgrade_success=run_pip_upgrade()

    # Verify environment regardless of upgrade success
    env_ok=verify_environment()

    print(""
" + "=" * 50)"

    if env_ok:
        print(" Environment verification successful!")
        print(" All required packages available")

        if not upgrade_success:
            print(
                "ℹ️ Note: Pip upgrade skipped due to network issues, but current environment is sufficient"
            )

        return 0
    else:
        print("❌ Environment verification failed!")
        print("Missing critical packages - cannot proceed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
