#!/bin/bash

# DoD verification script for issue 365: Golden "contract tests" (fixtures → pipeline)
# Verifies that valid fixtures flow through pipeline and invalid fixtures go to DLQ

set -e

echo "=== DoD Verification for Issue 365: Golden Contract Tests ==="
echo ""

# Check if required directories exist
echo "✓ Checking required directory structure..."
if [[ ! -d "contracts/tests" ]]; then
    echo "❌ contracts/tests directory not found"
    exit 1
fi

if [[ ! -d "contracts/examples/valid" ]]; then
    echo "❌ contracts/examples/valid directory not found"
    exit 1
fi

if [[ ! -d "contracts/examples/invalid" ]]; then
    echo "❌ contracts/examples/invalid directory not found"
    exit 1
fi

echo "✓ Directory structure verified"

# Check required files exist
echo ""
echo "✓ Checking required files..."

REQUIRED_FILES=(
    "contracts/tests/test_contracts_e2e.py"
    "contracts/examples/valid/valid-full-article.json"
    "contracts/examples/valid/valid-minimal-fields.json"
    "contracts/examples/valid/valid-french-article.json"
    "contracts/examples/valid/valid-empty-content.json"
    "contracts/examples/invalid/invalid-missing-article-id.json"
    "contracts/examples/invalid/invalid-missing-source-id.json"
    "contracts/examples/invalid/invalid-missing-url.json"
    "contracts/examples/invalid/invalid-missing-language.json"
    "contracts/examples/invalid/invalid-sentiment-out-of-range.json"
    "contracts/examples/invalid/invalid-wrong-type-article-id.json"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "❌ Required file not found: $file"
        exit 1
    fi
done

echo "✓ All required files found"

# Validate JSON fixtures
echo ""
echo "✓ Validating JSON fixture syntax..."

for json_file in contracts/examples/valid/*.json contracts/examples/invalid/*.json; do
    if ! python -m json.tool "$json_file" > /dev/null 2>&1; then
        echo "❌ Invalid JSON syntax in: $json_file"
        exit 1
    fi
done

echo "✓ All JSON fixtures have valid syntax"

# Run the E2E contract tests
echo ""
echo "✓ Running E2E contract tests..."

if ! python -m pytest contracts/tests/test_contracts_e2e.py -v --tb=short; then
    echo "❌ E2E contract tests failed"
    exit 1
fi

echo "✓ All E2E contract tests passed"

# Test valid fixtures - should pass validation
echo ""
echo "✓ Testing valid fixtures with ArticleIngestValidator..."

python << 'EOF'
import json
import sys
from pathlib import Path
from services.ingest.common.contracts import ArticleIngestValidator, DataContractViolation

validator = ArticleIngestValidator()
valid_dir = Path("contracts/examples/valid")

print(f"Testing {len(list(valid_dir.glob('*.json')))} valid fixtures...")

for fixture_file in valid_dir.glob("*.json"):
    try:
        with open(fixture_file, 'r') as f:
            data = json.load(f)
        
        validator.validate_article(data)
        print(f"✓ {fixture_file.name} - VALID")
        
    except DataContractViolation as e:
        print(f"❌ {fixture_file.name} - FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ {fixture_file.name} - ERROR: {e}")
        sys.exit(1)

print("✓ All valid fixtures passed validation")
EOF

# Test invalid fixtures - should fail validation
echo ""
echo "✓ Testing invalid fixtures with ArticleIngestValidator..."

python << 'EOF'
import json
import sys
from pathlib import Path
from services.ingest.common.contracts import ArticleIngestValidator, DataContractViolation

validator = ArticleIngestValidator()
invalid_dir = Path("contracts/examples/invalid")

print(f"Testing {len(list(invalid_dir.glob('*.json')))} invalid fixtures...")

for fixture_file in invalid_dir.glob("*.json"):
    try:
        with open(fixture_file, 'r') as f:
            data = json.load(f)
        
        try:
            validator.validate_article(data)
            print(f"❌ {fixture_file.name} - SHOULD HAVE FAILED but passed validation")
            sys.exit(1)
        except DataContractViolation:
            print(f"✓ {fixture_file.name} - CORRECTLY FAILED validation")
        
    except Exception as e:
        print(f"❌ {fixture_file.name} - UNEXPECTED ERROR: {e}")
        sys.exit(1)

print("✓ All invalid fixtures correctly failed validation")
EOF

# Check that tests run in CI environment
echo ""
echo "✓ Verifying CI compatibility..."

if command -v pytest &> /dev/null; then
    echo "✓ pytest is available"
else
    echo "❌ pytest not found in PATH"
    exit 1
fi

# Run existing tests to ensure we didn't break anything
echo ""
echo "✓ Running existing consumer tests to ensure no regression..."

if python -m pytest tests/e2e/consumer/ -v --tb=short -x; then
    echo "✓ Existing consumer tests still pass"
else
    echo "❌ Existing consumer tests failed - regression detected"
    exit 1
fi

echo ""
echo "=== DoD VERIFICATION COMPLETE ==="
echo ""
echo "✅ REQUIREMENTS SATISFIED:"
echo "   • contracts/tests/test_contracts_e2e.py implemented"
echo "   • contracts/examples/valid/*.json fixtures created"  
echo "   • contracts/examples/invalid/*.json fixtures created"
echo "   • Valid fixtures flow through producer→consumer→staging pipeline"
echo "   • Invalid fixtures are routed to DLQ and don't land in staging"
echo "   • Test suite is green locally and ready for CI"
echo ""
echo "🎉 Issue 365 implementation complete and verified!"
