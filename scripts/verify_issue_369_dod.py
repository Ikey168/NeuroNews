#!/usr/bin/env python3
"""
DoD Verification Script for Issue 369: Auto-generate types codegen

Verifies all Definition of Done criteria are met:
1. ✅ Code generation script from all contract schemas (Avro, JSON Schema)
2. ✅ Generated Pydantic models with validation
3. ✅ Build script integration
4. ✅ Anti-drift tooling to detect hand-rolled DTOs
5. ✅ CI/CD integration readiness
6. ✅ Documentation for generated types
"""

import os
import sys
import subprocess
import json
import ast
import importlib.util
from pathlib import Path
from typing import List, Dict, Any


class Issue369DoDVerifier:
    def __init__(self):
        self.base_path = Path("/workspaces/NeuroNews")
        self.generated_path = self.base_path / "services" / "generated"
        self.scripts_path = self.base_path / "scripts" / "contracts"
        self.contracts_path = self.base_path / "contracts"
        self.results = []

    def log(self, message: str, success: bool = True):
        """Log verification result"""
        status = "✅" if success else "❌"
        print(f"{status} {message}")
        self.results.append({"message": message, "success": success})

    def verify_codegen_script_exists(self) -> bool:
        """Verify code generation script exists and is comprehensive"""
        codegen_path = self.scripts_path / "codegen.py"
        
        if not codegen_path.exists():
            self.log("Code generation script missing", False)
            return False
        
        self.log("Code generation script exists")
        
        # Check script content
        content = codegen_path.read_text()
        required_features = [
            "class AvroTypeGenerator",
            "class JsonSchemaTypeGenerator", 
            "def generate_from_schema",
            "BaseModel",
            "Field",
            "generate_init_files"
        ]
        
        for feature in required_features:
            if feature not in content:
                self.log(f"Code generation script missing feature: {feature}", False)
                return False
        
        self.log("Code generation script has all required features")
        return True

    def verify_build_script_integration(self) -> bool:
        """Verify build script exists and integrates codegen"""
        build_script = self.base_path / "build_types.sh"
        
        if not build_script.exists():
            self.log("Build script missing", False)
            return False
        
        self.log("Build script exists")
        
        content = build_script.read_text()
        if "codegen.py" not in content:
            self.log("Build script doesn't integrate codegen", False)
            return False
        
        self.log("Build script integrates code generation")
        return True

    def verify_generated_types_exist(self) -> bool:
        """Verify types are generated from all schemas"""
        if not self.generated_path.exists():
            self.log("Generated types directory missing", False)
            return False
        
        # Check Avro directory
        avro_dir = self.generated_path / "avro"
        if not avro_dir.exists():
            self.log("Generated Avro types directory missing", False)
            return False
        
        # Check JSON Schema directory  
        jsonschema_dir = self.generated_path / "jsonschema"
        if not jsonschema_dir.exists():
            self.log("Generated JSON Schema types directory missing", False)
            return False
        
        self.log("Generated types directories exist")
        
        # Count generated files
        avro_files = list(avro_dir.glob("*_models.py"))
        jsonschema_files = list(jsonschema_dir.glob("*_models.py"))
        
        if len(avro_files) == 0:
            self.log("No Avro types generated", False)
            return False
        
        if len(jsonschema_files) == 0:
            self.log("No JSON Schema types generated", False)
            return False
        
        self.log(f"Generated {len(avro_files)} Avro type files")
        self.log(f"Generated {len(jsonschema_files)} JSON Schema type files")
        return True

    def verify_pydantic_models(self) -> bool:
        """Verify generated models are valid Pydantic"""
        python_files = list(self.generated_path.glob("**/*_models.py"))
        
        if not python_files:
            self.log("No generated model files found", False)
            return False
        
        valid_models = 0
        for file_path in python_files:
            try:
                content = file_path.read_text()
                
                # Check for Pydantic imports
                if "from pydantic import" not in content:
                    self.log(f"File {file_path.name} missing Pydantic imports", False)
                    continue
                
                # Check for BaseModel usage
                if "BaseModel" not in content:
                    self.log(f"File {file_path.name} missing BaseModel usage", False)
                    continue
                
                # Validate Python syntax
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    self.log(f"File {file_path.name} has syntax error: {e}", False)
                    continue
                
                valid_models += 1
                
            except Exception as e:
                self.log(f"Error checking {file_path.name}: {e}", False)
                continue
        
        if valid_models == 0:
            self.log("No valid Pydantic models found", False)
            return False
        
        self.log(f"Found {valid_models} valid Pydantic model files")
        return True

    def verify_import_structure(self) -> bool:
        """Verify generated modules can be imported"""
        # Check __init__.py files exist
        init_files = list(self.generated_path.glob("**/__init__.py"))
        
        if len(init_files) < 2:  # At least root and subdirs
            self.log("Missing __init__.py files for imports", False)
            return False
        
        self.log("Generated modules have proper __init__.py structure")
        
        # Test basic import
        sys.path.insert(0, str(self.base_path))
        try:
            import services.generated
            self.log("Generated types module imports successfully")
            return True
        except ImportError as e:
            self.log(f"Generated types import failed: {e}", False)
            return False

    def verify_anti_drift_tooling(self) -> bool:
        """Verify tooling exists to detect hand-rolled DTOs"""
        # Check if build script includes DTO detection
        build_script = self.base_path / "build_types.sh"
        content = build_script.read_text()
        
        if "hand-rolled" not in content.lower():
            self.log("Build script missing anti-drift DTO detection", False)
            return False
        
        self.log("Anti-drift tooling integrated in build script")
        return True

    def verify_documentation(self) -> bool:
        """Verify usage documentation exists"""
        readme_path = self.generated_path / "README.md"
        
        if not readme_path.exists():
            self.log("Generated types documentation missing", False)
            return False
        
        content = readme_path.read_text()
        required_sections = ["Usage", "Import", "Example", "Validation"]
        
        for section in required_sections:
            if section.lower() not in content.lower():
                self.log(f"Documentation missing {section} section", False)
                return False
        
        self.log("Generated types documentation complete")
        return True

    def verify_ci_cd_readiness(self) -> bool:
        """Verify CI/CD integration readiness"""
        # Check if build script is executable
        build_script = self.base_path / "build_types.sh"
        
        if not os.access(build_script, os.X_OK):
            self.log("Build script not executable for CI/CD", False)
            return False
        
        # Check if script can run in CI environment
        try:
            result = subprocess.run(
                ["./build_types.sh"],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                self.log(f"Build script fails in CI mode: {result.stderr[:200]}", False)
                return False
        except subprocess.TimeoutExpired:
            self.log("Build script timeout - too slow for CI", False)
            return False
        except Exception as e:
            self.log(f"Build script execution error: {e}", False)
            return False
        
        self.log("Build script ready for CI/CD integration")
        return True

    def verify_schema_coverage(self) -> bool:
        """Verify all contract schemas are covered"""
        # Count source schemas (excluding examples)
        avro_schemas = list(self.contracts_path.glob("**/*.avsc"))
        
        # Only count JSON Schema files, not examples
        json_schemas = []
        for json_file in self.contracts_path.glob("**/*.json"):
            # Skip example files
            if "examples" in str(json_file):
                continue
            json_schemas.append(json_file)
        
        # Count generated files
        generated_avro = list((self.generated_path / "avro").glob("*_models.py"))
        generated_json = list((self.generated_path / "jsonschema").glob("*_models.py"))
        
        if len(generated_avro) < len(avro_schemas):
            self.log(f"Missing Avro coverage: {len(avro_schemas)} schemas, {len(generated_avro)} generated", False)
            return False
        
        if len(generated_json) < len(json_schemas):
            self.log(f"Missing JSON Schema coverage: {len(json_schemas)} schemas, {len(generated_json)} generated", False)
            return False
        
        self.log(f"Full schema coverage: {len(avro_schemas)} Avro + {len(json_schemas)} JSON Schema")
        return True

    def run_verification(self) -> bool:
        """Run all DoD verifications"""
        print("🔍 Verifying Issue 369 Definition of Done")
        print("=" * 50)
        
        checks = [
            ("Code generation script exists", self.verify_codegen_script_exists),
            ("Build script integration", self.verify_build_script_integration),
            ("Generated types exist", self.verify_generated_types_exist),
            ("Pydantic models valid", self.verify_pydantic_models),
            ("Import structure works", self.verify_import_structure),
            ("Anti-drift tooling", self.verify_anti_drift_tooling),
            ("Documentation complete", self.verify_documentation),
            ("CI/CD readiness", self.verify_ci_cd_readiness),
            ("Schema coverage complete", self.verify_schema_coverage)
        ]
        
        success_count = 0
        for check_name, check_func in checks:
            print(f"\n📋 Checking: {check_name}")
            if check_func():
                success_count += 1
        
        print(f"\n{'=' * 50}")
        all_passed = success_count == len(checks)
        
        if all_passed:
            print("🎉 All DoD criteria satisfied for Issue 369!")
            print("✅ Auto-generate types codegen implementation complete")
        else:
            print(f"❌ {len(checks) - success_count} DoD criteria failed")
            print("🔧 Fix remaining issues before marking complete")
        
        return all_passed


if __name__ == "__main__":
    verifier = Issue369DoDVerifier()
    success = verifier.run_verification()
    
    if success:
        print(f"\n🎯 Issue 369 DoD Status: PASSED")
        sys.exit(0)
    else:
        print(f"\n❌ Issue 369 DoD Status: FAILED")
        sys.exit(1)
